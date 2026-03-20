import uuid
from fastapi import UploadFile
from .s3_config import s3_client, BUCKET_NAME

async def upload_image_to_s3(file: UploadFile) -> str:
    file_extension = file.filename.split(".")[-1]
    unique_key = f"uploads/{uuid.uuid4()}.{file_extension}"

    s3_client.upload_fileobj(
        file.file,
        BUCKET_NAME,
        unique_key,
        ExtraArgs={
            "ContentType": file.content_type
        }
    )

    image_url = f"https://{BUCKET_NAME}.s3.amazonaws.com/{unique_key}"
    return image_url
