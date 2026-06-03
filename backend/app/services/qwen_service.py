import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()



def generate_response(prompt: str,model:str) -> str:
    
    print("MODEL =", model)
    
    llm = ChatOpenAI(
        api_key = os.getenv("QWEN_API_KEY"), # type: ignore
        base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        model = model,
        
    )

    print("MODEL =", model)
    response = llm.invoke(prompt).content
    return str(response)

