'''
game.py

Commit 2 minimal runtime:
input() -> call LLM -> log -> print
'''

import json
import os
from pyexpat.errors import messages
import time
from pathlib import Path

PROMPT_PATH = Path("prompts/prompt_v1.txt")
LOG_PATH = "dialogue_log.jsonl"

def load_prompt_template(): #loading the prompt template from a file
    if not PROMPT_PATH.exists():
        raise RuntimeError(f"Prompt file not found: {PROMPT_PATH}")
    text = PROMPT_PATH.read_text(encoding="utf-8").strip()
    return text

def log_turn(user_text, assistant_text, model_id):
    row = {
        "timestamp": time.time(),
        "model": model_id,
        "user_input": user_text,
        "assistant_output": assistant_text,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def main():
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1") #Stops the model printing progess bars 
    model_id = os.getenv("LOCAL_MODEL", "Qwen/Qwen2.5-0.5B-Instruct") #Model being used for the time being
    max_new_tokens = int(os.getenv("LOCAL_MAX_NEW_TOKENS", "128")) #Max tokens, small for testing

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except Exception as exc:
        print(f"Startup error: transformers/torch missing ({exc})")
        return

    try:
        print(f"Loading local model: {model_id}")
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = AutoModelForCausalLM.from_pretrained(model_id)
        if tokenizer.pad_token_id is None: #Runtime error for padding tokens
            tokenizer.pad_token = tokenizer.eos_token
        model.generation_config.temperature = None #Will enable temp later. Just want the likely response for testing and also means it is reproducible meaning easier to debug and easier to compare changes.
        model.generation_config.top_p = None
        model.generation_config.top_k = None
    except Exception as exc:
        print(f"Startup error: failed to load model ({exc})")
        return

    print("Commit 3a - LLM chat ready. /quit or /exit to stop.")
    messages = [{"role": "system", "content": "You are a concise, helpful assistant."}] #Conditioning for the LLM, small for testing

    prompt_template = load_prompt_template()

    while True:
        try:
            user_text = input("You > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSession ended.")
            break

        if not user_text:
            continue
        if user_text.lower() in {"/quit", "/exit"}:
            print("Session ended.")
            break
        prompt_text = f"{prompt_template}\n\nPlayer input:\n{user_text}\n\nReturn JSON only." #New JSON only for easier parsing later. Need to ensure the LLM understands
        messages.append({"role": "user", "content": prompt_text})

        try:
            if hasattr(tokenizer, "apply_chat_template"):
                full_prompt = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )

            inputs = tokenizer(full_prompt, return_tensors="pt")
            inputs = {k: v.to(model.device) for k, v in inputs.items()}#Moving to model's device for ease

            with torch.no_grad():
                output_ids = model.generate( #Generation
                    **inputs,
                    do_sample=False,
                    max_new_tokens=max_new_tokens,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                )

            prompt_len = inputs["input_ids"].shape[1]
            completion_ids = output_ids[0][prompt_len:] #Taling the new tokens
            assistant_text = tokenizer.decode(completion_ids, skip_special_tokens=True).strip()
            if not assistant_text:
                assistant_text = "(empty response)"

            messages.append({"role": "assistant", "content": assistant_text})
            log_turn(user_text, assistant_text, model_id)
            print(f"LLM > {assistant_text}")
        except Exception as exc:
            print(f"Generation error: {exc}")

if __name__ == "__main__":
    main()
