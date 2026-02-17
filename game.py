'''
game.py

Commit 2 minimal runtime:
input() -> call LLM -> log -> print
'''

import json
import os
import time


LOG_PATH = "dialogue_log.jsonl"

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
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    model_id = os.getenv("LOCAL_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    max_new_tokens = int(os.getenv("LOCAL_MAX_NEW_TOKENS", "128"))

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
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token
        # Avoid warnings from incompatible default generation flags.
        model.generation_config.temperature = None
        model.generation_config.top_p = None
        model.generation_config.top_k = None
    except Exception as exc:
        print(f"Startup error: failed to load model ({exc})")
        return

    print("Minimal LLM chat ready. Type /quit to exit.")
    messages = [{"role": "system", "content": "You are a concise, helpful assistant."}]

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
        messages.append({"role": "user", "content": user_text})

        try:
            if hasattr(tokenizer, "apply_chat_template"):
                full_prompt = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
            else:
                full_prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\nassistant:"

            inputs = tokenizer(full_prompt, return_tensors="pt")
            inputs = {k: v.to(model.device) for k, v in inputs.items()}

            with torch.no_grad():
                output_ids = model.generate(
                    **inputs,
                    do_sample=False,
                    max_new_tokens=max_new_tokens,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                )

            prompt_len = inputs["input_ids"].shape[1]
            completion_ids = output_ids[0][prompt_len:]
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
