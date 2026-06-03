from app.graph.workflow import graph

res = graph.invoke({
    "topic":"what is the llm."
})

print(res)