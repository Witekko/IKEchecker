import os
import json
import logging
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger('core')

def configure_gemini():
    """Configures the Gemini API client lazily."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return False
    try:
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        logger.error("Failed to configure Gemini client: %s", str(e))
        return False

def generate_morning_brief(portfolio_data, username="Client", language_hint='en-US'):
    """
    Sends the parsed daily portfolio data to Gemini to generate 
    a highly personalized 3-sentence morning brief.
    """
    is_configured = configure_gemini()
    if not is_configured:
        return "I'm sorry, my AI systems are currently offline. Please configure the GEMINI_API_KEY in the .env file."

    prompt = f"""Act as an elite quantitative wealth analyst summarizing a portfolio for your client, {username}. 
    Write a comprehensive Morning Brief (3-4 sentences) based ONLY on the following multi-timeframe JSON data.

    1. Begin by stating today's exact PLN and percentage change (DO NOT state the total portfolio value).
    2. Focus strictly on today's performance. You have access to "This Week (WTD)" and "This Month (MTD)" data, but DO NOT write a weekly or monthly report every day. Only mention these broader trends if today's movement significantly alters or contrasts with them (e.g., today's drop wiped out the weekly gain).
    3. Identify the primary drivers of today's performance by highlighting up to the top 3 gaining AND bottom 3 losing assets. You MUST cite BOTH their percentage change AND their absolute PLN impact.
    4. For each asset that has entries under "News Headlines for Volatile Assets": simply state the headline TITLES exactly as written, and include each article's "link" as a markdown hyperlink for the user to open. DO NOT interpret whether the news explains the price movement. DO NOT draw conclusions. Let the user decide. If no headlines are provided for an asset, do not mention any news for it.

    Do not use robotic JSON syntax, deliver it as natural analytical prose.

    CRITICAL INSTRUCTION: You MUST translate and write your entire response exclusively in the language corresponding to this Accept-Language header: {language_hint}.
    
    Data:
    {json.dumps(portfolio_data, indent=2)}
    """

    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
            )
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini API Error (Morning Brief): {e}")
        return "Unable to connect to the advisor systems at this time. Please try again later."


def generate_root_cause_analysis(symbol, change_pct, news_headlines, language_hint='en-US'):
    """
    Takes an asset, its daily % change, and the 5 most recent news headlines,
    and asks the AI to find the likely root cause of the movement in 1 sentence.
    """
    is_configured = configure_gemini()
    if not is_configured:
        return "AI analysis offline. Missing API Key."

    # If there are no news headlines available
    if not news_headlines or len(news_headlines) == 0:
        return f"Market volatility. No specific news catalysts found for {symbol} today."

    formatted_news = "\n".join([f"- {h}" for h in news_headlines])

    prompt = f"""
    The asset {symbol} moved {change_pct:.2f}% today.
    Based ONLY on the following recent news headlines, explain the likely root cause of this movement.
    Explain it in exactly ONE concise sentence. Do not invent information. 
    If the headlines do not explain the movement, say: "Market volatility without specific news catalysts."

    CRITICAL INSTRUCTION: You MUST translate and write your entire response exclusively in the language corresponding to this Accept-Language header: {language_hint}.

    Headlines:
    {formatted_news}
    """

    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
            )
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini API Error (Root Cause Analyst): {e}")
        return "Analysis failed due to server error."

