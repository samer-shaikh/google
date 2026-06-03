
def get_channel_info(channel_url: str):

    return {
        "channel_name": "Learn With Samer",
        "subscribers": 1000
    }


def get_recent_videos(channel_url: str):

    return [
        {
            "title": "How I Built My First AI Agent",
            "description": "Learn AI agents"
        },
        {
            "title": "Data Science Roadmap 2026",
            "description": "Become a data scientist"
        }
    ]