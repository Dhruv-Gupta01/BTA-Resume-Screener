import json
from openai import OpenAI
import os
from dotenv import load_dotenv
import streamlit as st


# Load environment variables
load_dotenv()

def analyze_job_description(job_description, model="gpt-4.1"):
    """
    Analyzes a job description using GPT-4 and extracts structured requirements.
    Returns a dictionary with must-have, good-to-have, and additional screening criteria.
    
    Args:
        job_description (str): The job description text to analyze
        model (str): The OpenAI model to use for analysis
    """
    open_ai_key = st.secrets["openai-key"]
    client = OpenAI(api_key=open_ai_key['OPENAI_API_KEY'])
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": """You are an experienced technical recruiter and job posting analyst.
                    Your task is to extract a structured summary of candidate requirements from the job description.
                    These will be used to evaluate resumes later.
                    
                    ## Instructions:
                    1. Extract all **Must-Have Requirements**:
                       - Technical Skills: Essential technical skills
                       - Experience: Minimum years and type of relevant experience
                       - Qualifications: Mandatory degrees or certifications
                       - Core Responsibilities: Key duties that are non-negotiable
                    
                    2. Extract all **Good-to-Have Requirements**:
                       - Additional Skills: Preferred technical skills
                       - Extra Qualifications: Bonus education or certifications
                       - Bonus Experience: Extra experience that could add value
                    
                    3. Extract any **Additional Screening Criteria**:
                       - Filtering statements that affect eligibility
                       - Work policy conditions
                       - Availability constraints
                       - Discriminatory or biased phrasing
                       - Anything else that significantly affects who should or shouldn't apply
                    
                    Return all extracted data in the following JSON format.

                    ## Output Format:
                    {
                      "original_job_description": "The complete original job description text",
                      "must_have_requirements": {
                        "technical_skills": [],
                        "experience": "",
                        "qualifications": [],
                        "core_responsibilities": []
                      },
                      "good_to_have_requirements": {
                        "additional_skills": [],
                        "extra_qualifications": [],
                        "bonus_experience": []
                      },
                      "additional_screening_criteria": [
                        // List any additional filtering statements or constraints that impact applicant suitability
                      ]
                    }"""
                },
                {
                    "role": "user",
                    "content": f"Please extract a structured summary of the candidate requirements from the following job description. Do not add any prefixes or suffixes to the output. Directly output in JSON format.\n---\n## Job Description:\n{job_description}\n---"
                }
            ],
            temperature=0.19,
            max_tokens=1147
        )
        
        # Parse the response into a dictionary
        extracted_data = json.loads(response.choices[0].message.content)
        
        # Add the original job description to the output
        extracted_data["original_job_description"] = job_description
        
        return extracted_data
        
    except Exception as e:
        print(f"Error in analyze_job_description: {str(e)}")
        return None

def format_requirements_for_display(requirements):
    """
    Formats the extracted requirements into a readable format for display in Streamlit.
    Returns the same JSON structure but with formatted strings for display.
    """
    if not requirements:
        return {
            "original_job_description": "",
            "must_have_requirements": {
                "technical_skills": [],
                "experience": "",
                "qualifications": [],
                "core_responsibilities": []
            },
            "good_to_have_requirements": {
                "additional_skills": [],
                "extra_qualifications": [],
                "bonus_experience": []
            },
            "additional_screening_criteria": []
        }
    
    # Return the original JSON structure
    return requirements

def parse_edited_requirements(must_have_text, preferred_text, additional_text):
    """
    Parses the edited text fields back into the original JSON format.
    """
    try:
        # Parse must-have requirements
        must_have = {
            "technical_skills": [],
            "experience": "",
            "qualifications": [],
            "core_responsibilities": []
        }
        
        current_section = None
        for line in must_have_text.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if line.endswith(':'):
                current_section = line[:-1].lower().replace(' ', '_')
                continue
                
            if line.startswith('- '):
                item = line[2:].strip()
                if current_section == 'technical_skills':
                    must_have['technical_skills'].append(item)
                elif current_section == 'qualifications':
                    must_have['qualifications'].append(item)
                elif current_section == 'core_responsibilities':
                    must_have['core_responsibilities'].append(item)
                elif current_section == 'experience':
                    must_have['experience'] = item[2:].strip() if item.startswith('- ') else item
        
        # Parse good-to-have requirements
        good_to_have = {
            "additional_skills": [],
            "extra_qualifications": [],
            "bonus_experience": []
        }
        
        current_section = None
        for line in preferred_text.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if line.endswith(':'):
                current_section = line[:-1].lower().replace(' ', '_')
                continue
                
            if line.startswith('- '):
                item = line[2:].strip()
                if current_section == 'additional_skills':
                    good_to_have['additional_skills'].append(item)
                elif current_section == 'extra_qualifications':
                    good_to_have['extra_qualifications'].append(item)
                elif current_section == 'bonus_experience':
                    good_to_have['bonus_experience'].append(item)
        
        # Parse additional screening criteria
        additional_criteria = []
        for line in additional_text.split('\n'):
            line = line.strip()
            if line.startswith('- '):
                additional_criteria.append(line[2:].strip())
        
        return {
            "original_job_description": "",  # This will be filled in by the main app
            "must_have_requirements": must_have,
            "good_to_have_requirements": good_to_have,
            "additional_screening_criteria": additional_criteria
        }
        
    except Exception as e:
        print(f"Error parsing edited requirements: {str(e)}")
        return None 