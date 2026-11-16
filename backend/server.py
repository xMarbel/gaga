"""VILO — local-first live chat server. Not audited for public Internet deployment."""
import os, time, json, secrets, hashlib, hmac, re, sqlite3, asyncio, threading, mimetypes, uuid, io
from PIL import Image, ImageOps, UnidentifiedImageError
from pathlib import Path
from contextlib import contextmanager, closing
from fastapi import FastAPI, Request, Response, HTTPException, Depends, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('VILO_DATA_DIR',ROOT/'data')).resolve()
DATA.mkdir(parents=True,exist_ok=True)
UPLOADS=DATA/'uploads'; UPLOADS.mkdir(exist_ok=True)
PROFILE_MEDIA=DATA/'profile_media'; PROFILE_MEDIA.mkdir(exist_ok=True)
DB_PATH=DATA/'vilo.db'
LOCK=threading.RLock()
app=FastAPI(title='VILO',docs_url=None,redoc_url=None,openapi_url=None)
# An instance runs with a single uvicorn worker.
connected:dict[int,set[WebSocket]]={}
rate:dict[str,list[float]]={}

def db():
    c=sqlite3.connect(DB_PATH,timeout=20,check_same_thread=False)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA busy_timeout=20000')
    return c

@contextmanager
def transaction():
    with LOCK:
        c=db()
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except Exception:
            c.rollback(); raise
        finally:
            c.close()

def one(query,*args):
    with closing(db()) as c: return c.execute(query,args).fetchone()
def allrows(query,*args):
    with closing(db()) as c: return [dict(r) for r in c.execute(query,args).fetchall()]

def init_db():
    with transaction() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, email TEXT NOT NULL UNIQUE COLLATE NOCASE, pw TEXT NOT NULL, display_name TEXT NOT NULL, about TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '#7c5cf0', created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN ('dm','group','server')),name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',owner_id INTEGER REFERENCES users(id),created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS members(room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,role TEXT NOT NULL DEFAULT 'member',joined INTEGER NOT NULL,PRIMARY KEY(room_id,user_id));
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,user_id INTEGER REFERENCES users(id),bot_name TEXT,body TEXT NOT NULL DEFAULT '',kind TEXT NOT NULL DEFAULT 'text',ref_id INTEGER,attachment_id TEXT,attachment_name TEXT,created INTEGER NOT NULL,edited INTEGER,deleted INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room_id,id);
        CREATE TABLE IF NOT EXISTS reactions(message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,emoji TEXT NOT NULL,PRIMARY KEY(message_id,user_id,emoji));
        CREATE TABLE IF NOT EXISTS friendships(id INTEGER PRIMARY KEY, sender INTEGER NOT NULL REFERENCES users(id),receiver INTEGER NOT NULL REFERENCES users(id),status TEXT NOT NULL DEFAULT 'pending',created INTEGER NOT NULL, UNIQUE(sender,receiver));
        CREATE TABLE IF NOT EXISTS invites(code TEXT PRIMARY KEY,room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,by_user INTEGER NOT NULL REFERENCES users(id),max_uses INTEGER NOT NULL DEFAULT 30,used INTEGER NOT NULL DEFAULT 0,expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS polls(id INTEGER PRIMARY KEY,room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,question TEXT NOT NULL,creator INTEGER NOT NULL REFERENCES users(id),multiple INTEGER NOT NULL DEFAULT 0,anonymous INTEGER NOT NULL DEFAULT 0,created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS poll_options(id INTEGER PRIMARY KEY,poll_id INTEGER NOT NULL REFERENCES polls(id) ON DELETE CASCADE,label TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS poll_votes(poll_id INTEGER NOT NULL REFERENCES polls(id) ON DELETE CASCADE,option_id INTEGER NOT NULL REFERENCES poll_options(id),user_id INTEGER NOT NULL REFERENCES users(id),PRIMARY KEY(poll_id,option_id,user_id));
        CREATE TABLE IF NOT EXISTS bots(id INTEGER PRIMARY KEY,room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,owner_id INTEGER NOT NULL REFERENCES users(id),name TEXT NOT NULL,trigger TEXT NOT NULL,response TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY,room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,by_user INTEGER NOT NULL REFERENCES users(id),filename TEXT NOT NULL,stored TEXT NOT NULL,size INTEGER NOT NULL,created INTEGER NOT NULL);
        ''')
        # Compatible profile upgrade: do not delete existing users or messages.
        user_cols={r[1] for r in c.execute('PRAGMA table_info(users)')}
        for col,sql in {
            'status_text':"ALTER TABLE users ADD COLUMN status_text TEXT NOT NULL DEFAULT ''",
            'avatar_rev':"ALTER TABLE users ADD COLUMN avatar_rev INTEGER NOT NULL DEFAULT 0",
            'banner_rev':"ALTER TABLE users ADD COLUMN banner_rev INTEGER NOT NULL DEFAULT 0"
        }.items():
            if col not in user_cols: c.execute(sql)
        # Additive migration: old VILO databases are retained.
        cols={r[1] for r in c.execute('PRAGMA table_info(messages)')}
        if 'channel_id' not in cols:
            c.execute('ALTER TABLE messages ADD COLUMN channel_id INTEGER')
        c.executescript('''
          CREATE TABLE IF NOT EXISTS room_config(
             room_id INTEGER PRIMARY KEY REFERENCES rooms(id) ON DELETE CASCADE,
             rules TEXT NOT NULL DEFAULT 'Szanuj innych. Nie spamuj. Nie udostępniaj cudzych danych.',
             welcome TEXT NOT NULL DEFAULT 'Witaj na serwerze!',
             accent TEXT NOT NULL DEFAULT '#8b6cf3');
          CREATE TABLE IF NOT EXISTS channels(
             id INTEGER PRIMARY KEY,
             room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
             name TEXT NOT NULL,
             category TEXT NOT NULL DEFAULT 'TEKSTOWE',
             kind TEXT NOT NULL DEFAULT 'text' CHECK(kind IN ('text','announcement','voice')),
             position INTEGER NOT NULL DEFAULT 0,
             staff_only INTEGER NOT NULL DEFAULT 0,
             archived INTEGER NOT NULL DEFAULT 0,
             created INTEGER NOT NULL);
          CREATE INDEX IF NOT EXISTS idx_channels_room ON channels(room_id,position,id);
          CREATE TABLE IF NOT EXISTS custom_roles(
             id INTEGER PRIMARY KEY,
