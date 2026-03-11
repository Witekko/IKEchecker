import os
import json
import logging
from openai import OpenAI

logger = logging.getLogger('core')

# Configure OpenAI Client
# It will automatically look for OPENAI_API_KEY in the environment if not passed explicitly.
try:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
except Exception as e:
    logger.error("Failed to initialize OpenAI client: %s", str(e))
    client = None

def generate_morning_brief(portfolio_data):
    """
    Sends the parsed daily portfolio data to GPT-4o-mini to generate 
    a highly personalized 3-sentence morning brief.
    """
    if not client or not os.environ.get("OPENAI_API_KEY"):
        return "I'm sorry, my AI systems are currently offline. Please configure the OpenAI API key."

    prompt = f"""
    You are an elite, friendly wealth advisor. Your client (name: Witek) has just logged into their portfolio tracing dashboard.
    Write a 3-sentence 'Morning Brief' summarizing their performance based ONLY on the following JSON data.
    Address them warmly. Do not use robotic JSON syntax, speak conversationally.
    If the profit is negative, be reassuring but objective.
    
    Data:
    {json.dumps(portfolio_data, indent=2)}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a personalized, high-end financial AI advisor."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API Error (Morning Brief): {e}")
        return "Unable to connect to the advisor systems at this time. Please try again later."


def generate_root_cause_analysis(symbol, change_pct, news_headlines):
    """
    Takes an asset, its daily % change, and the 5 most recent news headlines,
    and asks the AI to find the likely root cause of the movement in 1 sentence.
    """
    if not client or not os.environ.get("OPENAI_API_KEY"):
        return "AI analysis offline."

    # If there are no news headlines available
    if not news_headlines or len(news_headlines) == 0:
        return f"Market volatility. No specific news catalysts found for {symbol} today."

    formatted_news = "\n".join([f"- {h}" for h in news_headlines])

    prompt = f"""
    The asset {symbol} moved {change_pct:.2f}% today.
    Based ONLY on the following recent news headlines, explain the likely root cause of this movement.
    Explain it in exactly ONE concise sentence. Do not invent information. 
    If the headlines do not explain the movement, say: "Market volatility without specific news catalysts."

    Headlines:
    {formatted_news}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a concise financial news analyst."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=100
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API Error (Root Cause Analyst): {e}")
        return "Analysis failed due to server error."
