"""Optional provider chain. Only curated FAQ text leaves the process."""
import json
import os
from functools import lru_cache
from urllib.request import Request, urlopen
from urllib.parse import quote


def post(url, payload, headers=None):
    req = Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', **(headers or {})})
    with urlopen(req, timeout=8) as response:
        return json.loads(response.read(65536))


@lru_cache(maxsize=1)
def local_generator(path):
    from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
    return pipeline('text2text-generation', model=AutoModelForSeq2SeqLM.from_pretrained(path, local_files_only=True),
                    tokenizer=AutoTokenizer.from_pretrained(path, local_files_only=True), device=-1)


def generate(doc):
    prompt = 'Paraphrase this platform FAQ answer concisely. Preserve all qualifications.\n' + doc['question'] + '\n' + doc['answer']
    if doc.get('related'):
        prompt += '\nRelated platform facts for context:\n' + '\n'.join(doc['related'])[:1500]
    for provider in ('gemini', 'ollama', 'huggingface'):
        try:
            if provider == 'gemini' and os.getenv('GEMINI_API_KEY') and os.getenv('GEMINI_MODEL'):
                model = quote(os.environ['GEMINI_MODEL'], safe='')
                data = post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                            {'contents': [{'parts': [{'text': prompt}]}]}, {'x-goog-api-key': os.environ['GEMINI_API_KEY']})
                answer = data['candidates'][0]['content']['parts'][0]['text']
            elif provider == 'ollama' and os.getenv('OLLAMA_URL'):
                answer = post(os.environ['OLLAMA_URL'].rstrip('/') + '/api/generate',
                              {'model': os.getenv('OLLAMA_MODEL', 'mistral'), 'prompt': prompt, 'stream': False})['response']
            elif provider == 'huggingface' and os.getenv('HF_MODEL_PATH'):
                answer = local_generator(os.environ['HF_MODEL_PATH'])(prompt, max_new_tokens=96)[0]['generated_text']
            else:
                continue
            if isinstance(answer, str) and 0 < len(answer.strip()) <= 1200:
                return {'reply': answer.strip(), 'provider': provider}
        except Exception:
            continue
    return {'reply': doc['answer'], 'provider': 'faq'}
