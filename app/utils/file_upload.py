"""
File upload utility: supports local storage and AWS S3.
"""

import os
import uuid
import aiofiles
from pathlib import Path
from app.core.config import settings
from loguru import logger


async def upload_file(content: bytes, filename: str, content_type: str) -> str:
    """Upload file and return public URL."""
    if settings.STORAGE_BACKEND == "s3":
        return await _upload_to_s3(content, filename, content_type)
    return await _upload_local(content, filename)


async def _upload_local(content: bytes, filename: str) -> str:
    upload_dir = Path(settings.LOCAL_UPLOAD_DIR)
    file_path = upload_dir / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)
    logger.info(f"File saved locally: {file_path}")
    return f"/uploads/{filename}"


async def _upload_to_s3(content: bytes, filename: str, content_type: str) -> str:
    try:
        import boto3
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        s3.put_object(
            Bucket=settings.AWS_S3_BUCKET,
            Key=filename,
            Body=content,
            ContentType=content_type,
            ACL="public-read",
        )
        url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{filename}"
        logger.info(f"File uploaded to S3: {url}")
        return url
    except Exception as e:
        logger.error(f"S3 upload failed: {e}")
        return await _upload_local(content, filename)
