import json
from openai import OpenAI
import os
from dotenv import load_dotenv
import streamlit as st

# Load environment variables
load_dotenv()

# Initialize OpenAI client


def analyze_resume(resume_text, requirements=None, model="o4-mini"):
    """
    Analyzes a resume against the structured requirements from the JD analyzer.
    Returns a comprehensive analysis including quantitative matches and qualitative assessment.
    
    Args:
        resume_text (str): The text content of the resume
        requirements (dict): The JSON output from the JD analyzer containing:
            - original_job_description
            - must_have_requirements
            - good_to_have_requirements
            - additional_screening_criteria
        model (str): The OpenAI model to use for analysis
    """
    open_ai_key = st.secrets["openai-key"]
    client = OpenAI(api_key=open_ai_key['OPENAI_API_KEY'])
    has_jd = requirements and any(k in requirements for k in [
        "original_job_description", "must_have_requirements", "good_to_have_requirements", "additional_screening_criteria"
    ])
    
    try:
        if has_jd:
            # Format the requirements for the prompt
            requirements_str = f"""
            Original Job Description:
            {requirements.get('original_job_description', '')}

            Must-Have Requirements:
            {json.dumps(requirements.get('must_have_requirements', {}), indent=2)}

            Good-to-Have Requirements:
            {json.dumps(requirements.get('good_to_have_requirements', {}), indent=2)}

            Additional Screening Criteria:
            {json.dumps(requirements.get('additional_screening_criteria', []), indent=2)}
            """
            
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": """You are a recruiter evaluating a candidate's resume against a given job description (JD). Based on the JD, evaluate whether the candidate meets the necessary requirements.

                        ## Step 1: Quantitative Check
                        Perform a Boolean (true/false) check for each requirement based on the candidate's resume:

                        - For each skill listed in `must_have_requirements` and `good_to_have_requirements`, determine if the candidate possesses it. Return true or false for each.
                        - For each `core_responsibility`, determine if the candidate has demonstrated it in their past work. Return true or false.
                        - For each `additional_screening_criteria`, return a boolean value indicating whether the candidate meets the condition (e.g., full-time, onsite position, work authorization, etc.).

                        ## Step 2: Qualitative Assessment
                        Now, switch to a recruiter-style qualitative assessment. Use your **intuition like a human** — go beyond what's explicitly stated. Read between the lines, infer intent, and use contextual clues from the resume and the JD to judge fit. Reference the results from Step 1 as part of your reasoning.

                        Assess the following:

                        - **Inferred Skills**: What skills can you infer from the candidate's projects or roles?
                        - **Project Gravity**: Were the projects academic or real-world, high-impact, production-ready, etc.?
                        - **Ownership and Initiative**: Did the candidate lead the work? Show initiative? Or just follow directions?
                        - **Transferability to Role**: How well would their experience transfer to this particular role? Will they onboard quickly?
                        - **Bonus Experience & Extra Qualifications**: If the JD lists any bonus criteria (e.g., fintech, B2B SaaS), consider that a positive signal even if not part of Step 1.

                        ## Step 3: Final Recommendation
                        After both steps, make a final call. Output "Yes" or "No" and summarize your reasoning concisely. 

                        ---

                        ### Output Format (strictly follow this JSON structure):

                        {
                        "requirement_match": {
                            "must_have_requirements": {
                            "technical_skills": {
                                "JavaScript": true,
                                "React.js": true,
                                "Node.js": true,
                                "SQL databases (especially PostgreSQL)": true,
                                "Version control systems (e.g., Git)": true
                            },
                            "experience": true,
                            "qualifications": true,
                            "core_responsibilities": {
                                "Build and maintain scalable frontend components using React.js": true,
                                "Develop backend services using Node.js and PostgreSQL": true,
                                "Integrate with third-party APIs and internal microservices": true,
                                "Participate in code reviews, sprint planning, and architectural discussions": false,
                                "Write unit and integration tests with Jest/Mocha": true
                            }
                            },
                            "good_to_have_requirements": {
                            "additional_skills": {
                                "TypeScript": true,
                                "GraphQL": false,
                                "CI/CD pipelines": true,
                                "Docker": true,
                                "Strong understanding of security best practices": false
                            }
                            },
                            "additional_screening_criteria": {
                            "Position is full-time and onsite at Bangalore office": true,
                            "Fresh graduates and part-time applicants will not be considered": false,
                            "Open only to candidates with valid Indian work authorization": true,
                            "Applications from women and underrepresented groups are especially encouraged": true
                            }
                        },
                        "qualitative_assessment": {
                            "inferred_skills_from_projects": ["JavaScript", "React.js", "Node.js", "Git", "PostgreSQL"],
                            "project_gravity": "Medium",
                            "ownership_and_initiative": "High",
                            "transferability_to_role": "Low",
                            "recruiter_style_summary": "The candidate has strong technical skills and has demonstrated ownership over impactful projects. They possess experience with React.js, Node.js, and PostgreSQL, and are a strong fit for this role. Bonus experience in fintech or B2B SaaS would be considered a strong plus."
                        },
                        "final_recommendation": "Yes",
                        "summary_of_key_factors": [
                            "Demonstrated experience in both frontend (React.js) and backend (Node.js, PostgreSQL) technologies.",
                            "End-to-end ownership of key projects, including integrations with third-party APIs.",
                            "Relevant project experience with a strong fit to the job requirements, especially in web development.",
                            "Bonus experience in fintech/B2B SaaS is a plus."
                        ]
                        }
                        """
                    },
                    {
                        "role": "user",
                        "content": f"""You are a recruiter evaluating a candidate's resume against a given job description. Act like a human recruiter—use your intuition and read between the lines to assess the candidate's suitability. First, perform a quantitative check to determine if the candidate meets each required skill, responsibility, and screening criterion. Then, provide a qualitative assessment, including inferred skills, project impact, ownership, and transferability, while considering the context beyond what's explicitly stated. Finally, give a recommendation ("Yes" or "No") with a brief explanation of the key factors that influenced your decision.

                        ## Job Requirements:
                        {requirements_str}

                        ## Resume:
                        {resume_text}

                        Output ONLY the JSON object as specified in the system prompt, with no additional text or formatting."""
                    }
                ],
            
                response_format={
                    "type": "json_object"
                },
                reasoning_effort="high",
                store=False
            )
            
            # Parse the response into a dictionary
            analysis = json.loads(response.choices[0].message.content)
            
            # Calculate score based on the analysis
            score = calculate_score(analysis)
            
            return {
                "score": score,
                "analysis": analysis
            }
        else:
            response = client.chat.completions.create(
                model=model,
                messages = [
                    {
                        "role": "system",
                        "content": """You are a recruiter analyzing a candidate's resume in the absence of a job description (JD). Your task is to extract and summarize useful information for a hiring team.

                        ## Step 1: Resume Analysis
                        Analyze the resume and extract:
                        - **Skills**: List all relevant technical and non-technical skills inferred from the candidate's resume. Include both explicitly stated and contextually inferred skills.
                        - **Key Projects/Experiences**: Highlight major projects or roles that demonstrate impact, complexity, or domain expertise.
                        - **Education and Certifications**: Note relevant degrees or certifications.

                        ## Step 2: Qualitative Assessment
                        Assess the candidate using recruiter-style judgment based on the resume:

                        - **Inferred Skills**: What skills are demonstrated through their work or academic projects?
                        - **Project Gravity**: Were the projects academic or real-world, impactful, or part of large-scale implementations?
                        - **Ownership and Initiative**: Did the candidate lead, innovate, or execute independently?
                        - **Career Trajectory and Growth**: Do they show upward growth, increasing responsibility, or domain specialization?

                        ## Step 3: Key Summary for Hiring Team
                        Create a summary of key factors that a hiring manager might use to decide whether to shortlist the candidate. Do not recommend "Yes" or "No" — just summarize strengths and flags.

                        ---

                        ### Output Format (strictly follow this JSON structure):

                        {
                        "resume_analysis": {
                            "skills": ["Python", "TensorFlow", "Power BI", "Data Cleaning"],
                            "key_projects_experiences": [
                            "Built a computer vision model using YOLOv8 for safety compliance",
                            "Developed dashboards for real-time production monitoring using Power BI"
                            ],
                            "education_certifications": [
                            "B.Tech in Computer Science",
                            "Google Cloud Certified: Professional Data Engineer"
                            ]
                        },
                        "qualitative_assessment": {
                            "inferred_skills_from_projects": ["YOLO", "PyTorch", "Pandas", "Cloud Deployment"],
                            "project_gravity": "High - Industrial-grade implementations",
                            "ownership_and_initiative": "Strong ownership with self-started project initiatives",
                            "career_trajectory_and_growth": "Clear growth from intern to project lead roles"
                        },
                        "summary_of_key_factors": [
                            "Strong computer vision and data science experience in real-world manufacturing settings",
                            "End-to-end ownership from model development to deployment and dashboarding",
                            "Relevant academic background and technical certifications"
                        ]
                        }
                        """
                            },
                            {
                                "role": "user",
                                "content": f"""You are a recruiter reviewing a candidate's resume without a specific job description. Analyze the resume and extract insights as per the system instructions.

                        ## Resume:
                        {resume_text}

                        Output ONLY the JSON object as specified above, with no additional text or formatting."""
                    }
                ],
            
                response_format={
                    "type": "json_object"
                },
                reasoning_effort="high",
                store=False
            )
            
            # Parse the response into a dictionary
            analysis = json.loads(response.choices[0].message.content)
            
            # Calculate score based on the analysis
            score = calculate_score(analysis)
            
            return {
                "score": "",
                "analysis": analysis
            }
        
    except Exception as e:
        print(f"Error in analyze_resume: {str(e)}")
        return None

def calculate_score(analysis):
    """
    Calculates a simple score by counting the number of true values in all boolean fields.
    Returns a string in format "X/Y" where X is the count of true values and Y is the total number of boolean fields.
    """
    try:
        # Initialize counters
        true_count = 0
        total_fields = 0
        
        # Get the requirement match section
        requirement_match = analysis.get("requirement_match", {})
        
        # Count in must_have_requirements
        must_have = requirement_match.get("must_have_requirements", {})
        
        # Technical skills
        tech_skills = must_have.get("technical_skills", {})
        true_count += sum(1 for v in tech_skills.values() if v is True)
        total_fields += len(tech_skills)
        
        # Experience and qualifications
        if isinstance(must_have.get("experience"), bool):
            if must_have["experience"] is True:
                true_count += 1
            total_fields += 1
            
        if isinstance(must_have.get("qualifications"), bool):
            if must_have["qualifications"] is True:
                true_count += 1
            total_fields += 1
        
        # Core responsibilities
        core_resp = must_have.get("core_responsibilities", {})
        true_count += sum(1 for v in core_resp.values() if v is True)
        total_fields += len(core_resp)
        
        # Count in good_to_have_requirements
        good_to_have = requirement_match.get("good_to_have_requirements", {})
        add_skills = good_to_have.get("additional_skills", {})
        true_count += sum(1 for v in add_skills.values() if v is True)
        total_fields += len(add_skills)
        
        # Count in additional_screening_criteria
        screening = requirement_match.get("additional_screening_criteria", {})
        true_count += sum(1 for v in screening.values() if v is True)
        total_fields += len(screening)
        
        # Return score as "X/Y"
        return f"{true_count}/{total_fields}"
        
    except Exception as e:
        print(f"Error calculating score: {str(e)}")
        return "0/0" 