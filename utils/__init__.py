from utils.broadcast import BroadcastManager
from utils.database import db
from yt_dlp.utils import DownloadError
from dotenv import load_dotenv
from itertools import combinations
from PIL import Image
from io import BytesIO
from yt_dlp import YoutubeDL
import requests, asyncio, re, os
import hashlib, time
from concurrent.futures import ThreadPoolExecutor
import aiohttp
from telethon import sync
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import (
    InputMediaUploadedDocument,
    DocumentAttributeAudio,
    InputMediaPhotoExternal,
    DocumentAttributeVideo
)
from FastTelethonhelper import fast_upload
from threading import Thread
import concurrent
from functools import lru_cache, partial
import io
import sys
from dataclasses import dataclass, field
from typing import Tuple, Any
from telethon.errors.rpcerrorlist import WebpageMediaEmptyError
from .helper import sanitize_query
