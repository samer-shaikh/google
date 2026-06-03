MODELS = {
    "normal": {
        "default": "qwen-plus"
    },

    "pro": {
        "default": "qwen-plus"
    },

    "plus": {
         # Heavy reasoning
        "research": "qwen-max",

        # Long-form generation
        "script": "qwen-max",

        # Creative brainstorming
        "video_idea": "qwen-plus",

        # SEO doesn't need max
        "seo": "qwen-plus",

        # Thumbnail prompt generation
        "thumbnail": "qwen-plus",

        # Metadata optimization
        "upload_optimizer": "qwen-plus",
        

        # Final YouTube packaging
        "youtube": "qwen-plus"
    }
}


def get_model(plan: str, task: str):
    if plan in ["normal", "pro"]:
        return MODELS[plan]["default"]

    return MODELS["plus"].get(task, "qwen-plus")