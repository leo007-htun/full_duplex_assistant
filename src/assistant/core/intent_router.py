import os
from jinja2 import Environment, FileSystemLoader

PROMPT_DIR = os.path.join(os.path.dirname(__file__), "../prompts")

def render_intent_prompt():
    env = Environment(loader=FileSystemLoader(PROMPT_DIR))
    template = env.get_template("intent_prompt.j2")
    return template.render()
