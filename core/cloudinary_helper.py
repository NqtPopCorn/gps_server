"""
Helper utilities for Cloudinary upload / delete operations.
"""
import cloudinary
import cloudinary.uploader
import cloudinary.api


def upload_image(file, folder: str) -> str:
    """Upload an image file to Cloudinary and return the secure URL."""
    result = cloudinary.uploader.upload(
        file,
        folder=folder,
        overwrite=True,
        resource_type="image",
    )
    return result["secure_url"]


def upload_audio(file, folder: str) -> str:
    """Upload an audio file to Cloudinary and return the secure URL."""
    result = cloudinary.uploader.upload(
        file,
        folder=folder,
        overwrite=True,
        resource_type="auto",
    )
    return result["secure_url"]


def delete_resources_by_prefix(prefix: str) -> None:
    """Delete all Cloudinary resources whose public_id starts with *prefix*."""
    cloudinary.api.delete_resources_by_prefix(prefix)
    try:
        cloudinary.api.delete_folder(prefix)
    except Exception:
        # folder may not be empty yet or may not exist – ignore
        pass
