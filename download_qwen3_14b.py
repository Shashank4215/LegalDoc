"""
Script to download Qwen3-14B-Instruct from HuggingFace
"""
import os
from huggingface_hub import snapshot_download
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Qwen3-14B model configuration
MODEL_NAME = "Qwen/Qwen3-14B-Instruct"  # Official Qwen3-14B Instruct model
LOCAL_MODEL_DIR = os.getenv("LOCAL_MODEL_DIR", "./models/qwen3-14b-instruct")

def download_model():
    """Download Qwen3-14B-Instruct model from HuggingFace"""
    try:
        logger.info(f"Starting download of {MODEL_NAME}...")
        logger.info(f"Model will be saved to: {LOCAL_MODEL_DIR}")
        logger.info("This may take a while (model is ~28GB)...")
        
        # Create directory if it doesn't exist
        os.makedirs(LOCAL_MODEL_DIR, exist_ok=True)
        
        # Download model files
        snapshot_download(
            repo_id=MODEL_NAME,
            local_dir=LOCAL_MODEL_DIR,
            local_dir_use_symlinks=False,
            resume_download=True
        )
        
        logger.info(f"✅ Model downloaded successfully to {LOCAL_MODEL_DIR}")
        logger.info("You can now update your config.py to use this model")
        
        return LOCAL_MODEL_DIR
        
    except Exception as e:
        logger.error(f"Error downloading model: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    download_model()

