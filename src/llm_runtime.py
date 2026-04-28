'''
src/llm_runtime.py

Minimal local Hugging Face runtime wrapper
Moved this from game.py to make it clearer + more modular + more industry standard
Still very basic
'''

import os
import time

class LocalLLM:
    def __init__(self):
        self.model_id = os.getenv("LOCAL_MODEL_ID", "").strip()
        self.max_new_tokens = None
        raw_tokens = os.getenv("LOCAL_MAX_NEW_TOKENS", "").strip()
        if raw_tokens:
            try:
                self.max_new_tokens = max(16, int(raw_tokens))
            except Exception:
                self.max_new_tokens = None
        self.device = "cuda"
        self.tokenizer = None
        self.model = None
        self.torch = None

    def load(self):
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1") #No progress bars.. no noise

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer 
        except Exception as exc:
            raise RuntimeError(f"transformers/torch missing ({exc})")

        self.torch = torch

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable. This runtime requires a CUDA-capable GPU.")
        
        #Can change this for other gpus
        self.device = "cuda" #Only suppoting CUDA which means running on my NVIDIA GPU, this is most common

        if not self.model_id:
            self.model_id = "Qwen/Qwen2.5-1.5B-Instruct"

        if self.max_new_tokens is None:
            self.max_new_tokens = 192

        t0 = time.time() #Timing how long it takes to load
        print(f"Loading local model: {self.model_id}")

        model_dtype = torch.float16
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id) #download tokeniser
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            dtype=model_dtype,
            low_cpu_mem_usage=True,
        )
        self.model.to(self.device)
        self.model.eval() 

        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # Safe speed knobs for NVIDIA cards.
        torch.backends.cuda.matmul.allow_tf32 = True  #Speeds up LLM as it speeds up matrix multiplications...
        torch.backends.cudnn.allow_tf32 = True

        elapsed = time.time() - t0
        print(f"Runtime device: {self.device}")
        print(f"Max new tokens: {self.max_new_tokens}")
        print(f"Local LLM ready in {elapsed:.1f}s.") #Debug

    def generate(self, messages): #Expecting lists of dicts with role and content
        if hasattr(self.tokenizer, "apply_chat_template"):
            full_prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            full_prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\nassistant:"

        inputs = self.tokenizer(full_prompt, return_tensors="pt")
        inputs = {k: v.to(self.model.device) for k, v in inputs.items()}

        with self.torch.no_grad():
            output_ids = self.model.generate( 
                **inputs,
                do_sample=True,
                max_new_tokens=self.max_new_tokens,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                use_cache=True,
            )

        prompt_len = inputs["input_ids"].shape[1]
        completion_ids = output_ids[0][prompt_len:]
        text = self.tokenizer.decode(completion_ids, skip_special_tokens=True).strip()
        if not text:
            return "(empty response)"
        return text

    def count_tokens_text(self, text): 
        if not self.tokenizer:
            return max(1, len(str(text or "").split()))
        try:
            tokens = self.tokenizer(str(text or ""), return_tensors="pt")
            return int(tokens["input_ids"].shape[1])
        except Exception:
            return max(1, len(str(text or "").split()))
