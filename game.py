'''
game.py

Commit 3b runtime:
input() -> build prompt -> call LLM -> parse/validate JSON -> log -> print
'''

import json
import os
import time
from pathlib import Path

PROMPT_PATH = Path("prompts/prompt_v1.txt")
LOG_PATH = "dialogue_log.jsonl"

def load_prompt_template(): #loading the prompt template from a file
    if not PROMPT_PATH.exists():
        raise RuntimeError(f"Prompt file not found: {PROMPT_PATH}")
    text = PROMPT_PATH.read_text(encoding="utf-8").strip()
    return text

def extract_json_object(raw_text): #Now extracting the Json from the LLM output
    text = str(raw_text or "").strip() 
    if not text:
        return None 
    try: #We parse the whole thing first, hwoever this is unlikely that the LLM will output perfectly
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{") #Failing that, we find the first json object and parse that
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}": #Finding the end of the json object
            depth -= 1
            if depth == 0:
                chunk = text[start : i + 1]
                try:
                    return json.loads(chunk)
                except Exception:
                    return None
    return None

def validate_output(parsed): #Ensure it has the correct types
    errors = []
    if not isinstance(parsed, dict):
        return False, None, ["Output is not a JSON object."]

    required = {
        "npc_dialogue": str,
        "state_updates": dict,
        "memory_summary": str,
    }

    for key, expected_type in required.items():
        if key not in parsed:
            errors.append(f"Missing required key: {key}")
            continue
        if not isinstance(parsed[key], expected_type):
            errors.append(
                f"Key '{key}' must be {expected_type.__name__}, got {type(parsed[key]).__name__}"
            )

    extra = set(parsed.keys()) - set(required.keys())
    if extra:
        errors.append(f"Unexpected keys present: {sorted(extra)}")

    if errors:
        return False, None, errors
    return True, parsed, []

def log_turn(
    user_text,
    prompt_text,
    raw_output,
    parsed_output,
    valid,
    errors,
    model_id,
    attempt_count=1,
    recovered_after_retry=False,
):
    row = {
        "timestamp": time.time(),
        "model": model_id,
        "user_input": user_text,
        "prompt": prompt_text,
        "raw_output": raw_output,
        "parsed_output": parsed_output,
        "valid": valid,
        "errors": errors,
        "attempt_count": attempt_count,
        "recovered_after_retry": recovered_after_retry,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")

def generate_once(tokenizer, model, torch, messages, max_new_tokens): 
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
    return assistant_text 


def main():
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1") #Stops the model printing progess bars 
    model_id = os.getenv("LOCAL_MODEL", "Qwen/Qwen2.5-0.5B-Instruct") #Model being used for the time being
    max_new_tokens = int(os.getenv("LOCAL_MAX_NEW_TOKENS", "64")) #Max tokens, small for testing

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

    print("Commit 3c - LLM JSON loop ready. /quit or /exit to stop.") 
    messages = [{"role": "system", "content": "You are Eli, a grounded fantasy NPC. Stay in character."}] 

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
            print("Generating...")
            attempt_count = 1
            recovered_after_retry = False

            assistant_text = generate_once(tokenizer, model, torch, messages, max_new_tokens)
            parsed = extract_json_object(assistant_text)
            valid, parsed_output, errors = validate_output(parsed)

            if not valid: #Only allowing for one retry, if the LLM was quicker then could be more... Maybe good for evaluation
                attempt_count = 2
                retry_prompt = ( 
                    f"{prompt_text}\n\n" #Reminder of original prompt when the LLM fails
                    "Previous output was invalid.\n"
                    f"Errors: {errors}\n"
                    "Return ONLY valid JSON with keys: npc_dialogue, state_updates, memory_summary."
                )
                retry_messages = messages[:-1] + [{"role": "user", "content": retry_prompt}]
                assistant_text = generate_once(tokenizer, model, torch, retry_messages, max_new_tokens)
                parsed = extract_json_object(assistant_text)
                valid, parsed_output, errors = validate_output(parsed)
                recovered_after_retry = valid

            if valid:
                messages.append({"role": "assistant", "content": assistant_text})

            log_turn(
                user_text,
                prompt_text,
                assistant_text,
                parsed_output,
                valid,
                errors,
                model_id,
                attempt_count=attempt_count,
                recovered_after_retry=recovered_after_retry,
            )

            if not valid:
                print("LLM > (invalid JSON output)")
                print(f"Errors: {errors}")
                continue

            print(f"LLM > {parsed_output['npc_dialogue']}")
        except Exception as exc:
            print(f"Generation error: {exc}")

if __name__ == "__main__":
    main()
