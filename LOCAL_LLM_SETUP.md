# Local LLM Setup Guide (Qwen3-14B)

This guide explains how to set up and use Qwen3-14B locally instead of Groq API.

## Prerequisites

- Python 3.8+
- CUDA-capable GPU (recommended: 40GB+ VRAM for Qwen3-14B)
- At least 100GB free disk space for the model

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- `vllm` - High-performance inference engine (optional, for faster inference)
- `huggingface-hub` - For downloading models
- `transformers` - For model loading
- `langchain-community` - For LangChain integration

## Step 2: Download Qwen3-14B Model

Run the download script:

```bash
python download_qwen3_14b.py
```

This will download the model to `./models/qwen3-14b-instruct/` (approximately 28GB).

**Note:** The download may take a while depending on your internet connection. The script supports resume, so you can interrupt and restart if needed.

## Step 3: Configure Environment

Create a `.env` file (or update existing one) with the following settings:

```bash
# Enable local LLM
LOCAL_LLM_ENABLED=True

# Model path (where you downloaded it)
LOCAL_MODEL_PATH=./models/qwen3-14b-instruct

# Backend: 'transformers' (works out of box) or 'vllm' (faster, requires separate setup)
LOCAL_LLM_BACKEND=transformers

# Device: 'cuda' for GPU or 'cpu' for CPU (CPU is very slow)
LOCAL_LLM_DEVICE=cuda

# GPU memory utilization (0.0 to 1.0)
LOCAL_LLM_GPU_MEMORY_UTILIZATION=0.9

# Maximum context length
LOCAL_LLM_MAX_MODEL_LEN=8192
```

## Step 4: Run Your Application

Start your FastAPI server:

```bash
uvicorn chat_api:app --reload --port 8000
```

The application will automatically:
1. Detect that `LOCAL_LLM_ENABLED=True`
2. Load the Qwen3-14B model from the specified path
3. Use it for all chat queries

## Monitoring Token Generation

The system includes built-in monitoring that logs:
- ⏱️ **Duration**: Time taken for inference
- 📊 **Token counts**: Input/output/total tokens
- ⚡ **Speed**: Tokens per second

Example log output:
```
🚀 LLM inference started | Input tokens: ~150
✅ LLM inference completed
   ⏱️  Duration: 3.45s
   📊 Input tokens: ~150 | Output tokens: ~200 | Total: ~350
   ⚡ Speed: 57.97 tokens/s
```

## Switching Back to Groq

To switch back to Groq API, simply set:

```bash
LOCAL_LLM_ENABLED=False
```

## Performance Tips

### For Faster Inference (vLLM)

1. Install vLLM: `pip install vllm`
2. Start vLLM server in a separate terminal:
   ```bash
   python -m vllm.entrypoints.openai.api_server \
     --model ./models/qwen3-14b-instruct \
     --tensor-parallel-size 1 \
     --gpu-memory-utilization 0.9
   ```
3. Update your config to use the OpenAI-compatible API endpoint

### For Lower Memory Usage

- Reduce `LOCAL_LLM_GPU_MEMORY_UTILIZATION` (e.g., 0.7)
- Use quantization (requires additional setup)
- Consider using a smaller model like Qwen2.5-7B

## Troubleshooting

### Out of Memory Error

- Reduce `LOCAL_LLM_GPU_MEMORY_UTILIZATION` to 0.7 or lower
- Reduce `LOCAL_LLM_MAX_MODEL_LEN` to 4096
- Ensure you have enough GPU memory (Qwen3-14B needs ~28GB VRAM)

### Model Not Found

- Verify the model path in `LOCAL_MODEL_PATH`
- Ensure the download completed successfully
- Check that the path contains `config.json` and model files

### Slow Inference

- Ensure you're using `LOCAL_LLM_DEVICE=cuda` (not cpu)
- Consider using vLLM backend for better performance
- Check GPU utilization with `nvidia-smi`

### Import Errors

- Ensure all dependencies are installed: `pip install -r requirements.txt`
- For `langchain_community`, install: `pip install langchain-community`

## Configuration Options

All configuration options are available in `config.py` and can be set via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LOCAL_LLM_ENABLED` | `False` | Enable/disable local LLM |
| `LOCAL_MODEL_PATH` | `./models/qwen3-14b-instruct` | Path to downloaded model |
| `LOCAL_MODEL_NAME` | `Qwen/Qwen3-14B-Instruct` | HuggingFace model ID |
| `LOCAL_LLM_BACKEND` | `transformers` | Backend: `transformers` or `vllm` |
| `LOCAL_LLM_DEVICE` | `cuda` | Device: `cuda` or `cpu` |
| `LOCAL_LLM_TENSOR_PARALLEL_SIZE` | `1` | Number of GPUs (for multi-GPU) |
| `LOCAL_LLM_MAX_MODEL_LEN` | `8192` | Maximum context length |
| `LOCAL_LLM_GPU_MEMORY_UTILIZATION` | `0.9` | GPU memory usage (0.0-1.0) |

## Next Steps

Once set up, your chatbot will use the local Qwen3-14B model for all queries, providing:
- ✅ No API costs
- ✅ Complete data privacy
- ✅ Customizable inference parameters
- ✅ Token monitoring and logging

Enjoy your local LLM setup! 🚀

