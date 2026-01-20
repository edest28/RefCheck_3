"""
AI-powered job description generation.
"""
import re
import json
import requests


def generate_job_description_with_claude(
    title,
    department,
    seniority,
    location,
    focus_areas,
    company_name,
    company_website,
    api_key,
):
    """Generate a comprehensive job description using Claude.

    Args:
        focus_areas: User-provided bullet points or notes to expand into full JD
        company_website: Optional company website URL

    Returns dict:
      {
        "headline": str,
        "summary": str,
        "responsibilities": [str],
        "requirements": [str],
        "nice_to_haves": [str],
        "benefits": [str],
        "full_description": str  # Complete formatted JD text
      }
    """
    if not api_key:
        return {
            "headline": f"{title} ({location or 'Remote'})",
            "summary": f"Join {company_name or 'our team'} as a {seniority or ''} {title}.",
            "responsibilities": [
                "Ship high-quality features end-to-end",
                "Collaborate cross-functionally with product and design",
                "Own production reliability for your area",
            ],
            "requirements": [
                "Relevant experience for the role",
                "Strong communication and ownership",
            ],
            "nice_to_haves": [
                "Experience in a high-growth environment",
            ],
            "benefits": [],
            "full_description": "",
        }

    # Enhanced prompt that generates extensive JD from bullet points
    prompt = f"""You are an expert job description writer. Create a comprehensive, professional job description based on the following information.

Company: {company_name or 'N/A'}
Company Website: {company_website or 'N/A'}
Job Title: {title}
Department: {department or 'N/A'}
Seniority Level: {seniority or 'N/A'}
Location: {location or 'N/A'}

Key Points / Requirements (expand these into a full job description):
{focus_areas or 'General role requirements'}

Instructions:
1. Write an engaging, professional job description that would attract top talent
2. Expand the key points into detailed responsibilities (8-12 bullet points)
3. Create comprehensive requirements (6-10 items) covering skills, experience, and qualifications
4. Include nice-to-have qualifications (3-5 items)
5. Add a benefits section if appropriate (4-6 items)
6. Write a compelling 2-3 sentence summary/overview
7. Create a professional headline

Return ONLY valid JSON with this exact shape:
{{
  "headline": "Engaging headline for the role",
  "summary": "2-3 sentence compelling overview of the role and company",
  "responsibilities": ["Detailed responsibility 1", "Detailed responsibility 2", ...],
  "requirements": ["Required skill/experience 1", "Required skill/experience 2", ...],
  "nice_to_haves": ["Nice to have 1", "Nice to have 2", ...],
  "benefits": ["Benefit 1", "Benefit 2", ...],
  "full_description": "Complete formatted job description text ready to use (markdown format)"
}}

IMPORTANT: In the full_description, make all section headers bold using markdown syntax. For example:
- "## **Responsibilities**" (not "## Responsibilities")
- "## **Requirements**" (not "## Requirements")
- All section headers should use **bold** markdown formatting.

Make the description extensive, professional, and appealing to candidates. Expand on the key points provided to create a thorough job description."""
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-3-5-haiku-20241022",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        content = result.get("content", [{}])[0].get("text", "{}")
        json_match = re.search(r"\{[\s\S]*\}", content)
        parsed = json.loads(json_match.group() if json_match else content)
        
        # If full_description wasn't provided, construct it from the parts
        if "full_description" not in parsed or not parsed.get("full_description"):
            parts = []
            if parsed.get("headline"):
                parts.append(f"# **{parsed['headline']}**\n")
            if parsed.get("summary"):
                parts.append(f"{parsed['summary']}\n")
            if parsed.get("responsibilities"):
                parts.append("\n## **Responsibilities**\n")
                for r in parsed["responsibilities"]:
                    parts.append(f"- {r}\n")
            if parsed.get("requirements"):
                parts.append("\n## **Requirements**\n")
                for r in parsed["requirements"]:
                    parts.append(f"- {r}\n")
            if parsed.get("nice_to_haves"):
                parts.append("\n## **Nice to Have**\n")
                for n in parsed["nice_to_haves"]:
                    parts.append(f"- {n}\n")
            if parsed.get("benefits"):
                parts.append("\n## **Benefits**\n")
                for b in parsed["benefits"]:
                    parts.append(f"- {b}\n")
            parsed["full_description"] = "".join(parts)
        
        # Ensure headers in full_description are bolded (if AI didn't do it)
        if parsed.get("full_description"):
            import re
            # Bold markdown headers (## Header -> ## **Header**)
            full_desc = parsed["full_description"]
            # Match headers like "## Header" or "### Header" and bold the text
            full_desc = re.sub(r'^(#{2,})\s+([^\n]+)$', r'\1 **\2**', full_desc, flags=re.MULTILINE)
            parsed["full_description"] = full_desc
        
        return parsed
    except Exception as e:
        print(f"Error generating job description: {e}")
        return None
