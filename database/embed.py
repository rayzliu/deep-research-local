#!/usr/bin/env python3

import os
from openai import OpenAI

client = OpenAI(
	api_key=os.getenv("OPENAI_API_KEY"),
	base_url="https://api.chatanywhere.tech/v1"
)

def get_text_embedding(text_input, model="text-embedding-3-large"):
	model = os.environ.get("ALTERNATIVE_EMBEDDING_MODEL", model)
	try:
		response = client.embeddings.create(
			input=text_input,
			model=model
		)
		# For single input, the embedding is in the first data object
		return response.data[0].embedding
	except Exception as e:
		print(f"An error occurred: {e}")
		raise RuntimeError(e)
		return None
