import json
import time
from openai import OpenAI, RateLimitError, APIStatusError
from dotenv import load_dotenv
import streamlit as st

# Load environment variables
load_dotenv()

# Initialize OpenAI client


FIREWORKS_MODEL = "accounts/fireworks/models/gpt-oss-120b"

def analyze_resume(resume_text, requirements=None, model=FIREWORKS_MODEL):
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
        model (str): The Fireworks model id to use for analysis
    """
    fireworks_key = st.secrets["fireworks-key"]
    client = OpenAI(api_key=fireworks_key['FIREWORKS_API_KEY'], base_url="https://api.fireworks.ai/inference/v1")
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
                reasoning_effort="medium"
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
                reasoning_effort="medium"
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

def analyze_resume_for_sheet(resume_text, job_description, model=FIREWORKS_MODEL, api_key=None, criteria=None, jd_weight=0):
    """
    Single-call resume evaluator - the core "score a resume against a JD"
    primitive shared by the Streamlit sheet flow and the standalone API
    backend. Given the raw JD text and a resume's text, extracts the
    candidate's skills and strongest programming language, plus a short
    prose summary and a JD-fit score, in one flat JSON object.
    Does NOT extract name/email/phone/experience - those are assumed to
    already exist as manually-entered columns in the sheet (or are the
    calling application's own concern, for API callers).

    Args:
        resume_text (str): The text content of the resume
        job_description (str): The raw job description text
        model (str): The Fireworks model id to use for analysis
        api_key (str, optional): Fireworks API key. If not given, falls back
            to st.secrets["fireworks-key"]["FIREWORKS_API_KEY"] (Streamlit
            usage). Non-Streamlit callers (e.g. api.py) must pass this.
        criteria (list[dict], optional): User-defined weighted scoring
            rubric, e.g. [{"text": "4 to 7 years of experience building
            production systems, not just internal tools", "weight": 40}].
            When given, the model scores the resume against EACH criterion
            independently (0-100).
        jd_weight (float, optional): Weight to give the model's own holistic
            "fit against the JD as a whole" judgment, treated as one more
            entry alongside `criteria` in the same weighted average - e.g.
            jd_weight=30 with two criteria weighted 40 and 30 means the
            final score is 30% general JD fit, 40%/30% those two specific
            criteria. Default 0 means the JD contributes nothing to the
            score directly (criteria only, or - if criteria is also empty -
            legacy single-holistic-score behavior, unchanged from before
            this parameter existed).

        The final "score" is always a weighted average computed here in
        code (not by the model) whenever criteria and/or jd_weight are
        used - this keeps the weighting arithmetic deterministic and
        auditable instead of trusting the LLM to do the math itself.
        Weights don't need to sum to 100 - they're normalized automatically.

    Returns:
        dict with keys: skills, strongest_language, summary, score (int 0-100),
        and - only when `criteria` and/or `jd_weight` were used - a
        criteria_breakdown list of {criterion, weight, score} showing every
        sub-score (including a "Overall fit to the job description as a
        whole" entry when jd_weight > 0) that produced the final weighted
        score. Returns None on failure.
    """
    if api_key is None:
        api_key = st.secrets["fireworks-key"]["FIREWORKS_API_KEY"]
    client = OpenAI(api_key=api_key, base_url="https://api.fireworks.ai/inference/v1")

    # Drop any criteria with a non-positive weight - they'd contribute
    # nothing to the weighted average and just add prompt noise.
    criteria = [c for c in (criteria or []) if c.get("text", "").strip() and float(c.get("weight", 0)) > 0]
    try:
        jd_weight = float(jd_weight or 0)
    except (TypeError, ValueError):
        jd_weight = 0
    use_jd_score = jd_weight > 0
    JD_LABEL = "Overall fit to the job description as a whole"

    max_retries = 4
    retry_wait_seconds = 20  # grows each attempt: 20s, 40s, 60s, 80s

    if criteria or use_jd_score:
        criteria_list_text = "\n".join(f"{i + 1}. {c['text']}" for i, c in enumerate(criteria))
        rubric_block = f"""

                        ## Rubric Criteria:
                        {criteria_list_text}""" if criteria else ""

        criteria_scores_instruction = (
            f"criteria_scores: for EACH numbered criterion below, judge how well the resume satisfies THAT SPECIFIC criterion on a 0-100 scale (0 = does not satisfy it at all, 100 = fully satisfies it), independent of the others and independent of the JD as a whole. Return exactly {len(criteria)} entries, in the SAME ORDER as listed, one per criterion - do not skip, merge, or reorder any."
            if criteria else
            "criteria_scores: return an empty list [] - there are no rubric criteria to score."
        )
        jd_score_instruction = (
            "\n                        5. overall_jd_fit_score: judge the resume's overall fit against the job description AS A WHOLE (0-100), independent of the specific rubric criteria above - this is your general recruiter judgment of the full JD match."
            if use_jd_score else ""
        )
        jd_score_example = ',\n                          "overall_jd_fit_score": 65' if use_jd_score else ""

        example_criteria_scores = f'[\n                            {{"criterion": "{criteria[0]["text"]}", "score": 78}}\n                          ]' if criteria else "[]"

        system_prompt = f"""You are a recruiter evaluating a resume against a job description{" and a specific weighted scoring rubric" if criteria else ""}.

                        ## Task
                        1. skills: a comma-separated list of the candidate's technical and relevant non-technical skills (explicit and reasonably inferred from their projects/roles).
                        2. strongest_language: the ONE programming language the candidate has the most hands-on, production-level experience in, based solely on their resume (not the JD) - judge from depth/recency/volume of work shown, not just first-listed skill. A single language name (e.g. "Python"), or "" if none can be determined.
                        3. Write a short recruiter-style summary (3-5 sentences, plain text, no markdown) covering the candidate's experience, key projects, and how well they fit the job description - mention concrete strengths and gaps relative to {"the rubric criteria and the JD" if criteria else "the JD"}.
                        4. {criteria_scores_instruction}{jd_score_instruction}{rubric_block}

                        ## Output Format (strictly follow this JSON structure, no extra text):
                        {{
                          "skills": "Python, Django, REST APIs, PostgreSQL, AWS, Docker",
                          "strongest_language": "Python",
                          "summary": "The candidate has 4 years of backend engineering experience building REST APIs in Python/Django and deploying on AWS.",
                          "criteria_scores": {example_criteria_scores}{jd_score_example}
                        }}

                        If skills or strongest_language cannot be found, use an empty string (""). Do NOT include a top-level "score" field - the final score is computed separately from criteria_scores{" and overall_jd_fit_score" if use_jd_score else ""}."""

        user_prompt = f"""Extract the candidate's skills and strongest language, write a summary, and score the resume as per the system instructions.

                        ## Job Description{" (context for interpreting the rubric criteria" + ("" if use_jd_score else ", not scored directly") + ")" if criteria else ""}:
                        {job_description}

                        ## Resume:
                        {resume_text}

                        Output ONLY the JSON object as specified in the system prompt, with no additional text or formatting."""
    else:
        system_prompt = """You are a recruiter evaluating a resume against a job description.

                        ## Task
                        1. skills: a comma-separated list of the candidate's technical and relevant non-technical skills (explicit and reasonably inferred from their projects/roles).
                        2. strongest_language: the ONE programming language the candidate has the most hands-on, production-level experience in, based solely on their resume (not the JD) - judge from depth/recency/volume of work shown, not just first-listed skill. A single language name (e.g. "Python"), or "" if none can be determined.
                        3. Write a short recruiter-style summary (3-5 sentences, plain text, no markdown) covering the candidate's experience, key projects, and how well they fit the job description - mention concrete strengths and gaps relative to the JD.
                        4. Score the candidate's overall fit against the job description on a 0-100 scale (0 = no fit, 100 = perfect fit), based on required skills, experience level, and responsibilities matched.

                        ## Output Format (strictly follow this JSON structure, no extra text):
                        {
                          "skills": "Python, Django, REST APIs, PostgreSQL, AWS, Docker",
                          "strongest_language": "Python",
                          "summary": "The candidate has 4 years of backend engineering experience building REST APIs in Python/Django and deploying on AWS. They have led feature delivery end-to-end on production systems, which aligns well with the JD's need for backend ownership. They lack direct Kubernetes experience, which the JD lists as a plus. Overall a strong match for the core technical requirements.",
                          "score": 78
                        }

                        If skills or strongest_language cannot be found, use an empty string (""), and still provide your best-effort score."""

        user_prompt = f"""Extract the candidate's skills and strongest language, write a summary, and score the fit as per the system instructions.

                        ## Job Description:
                        {job_description}

                        ## Resume:
                        {resume_text}

                        Output ONLY the JSON object as specified in the system prompt, with no additional text or formatting."""

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={
                    "type": "json_object"
                },
                reasoning_effort="medium",
                max_completion_tokens=4096
            )

            record = json.loads(response.choices[0].message.content)

            # The model doesn't always use the exact key names requested - fall
            # back to common aliases before defaulting.
            def pick(*keys, default=""):
                for k in keys:
                    if record.get(k) not in (None, ""):
                        return record[k]
                return default

            # Skills sometimes come back as a list instead of a string - flatten.
            def as_text(value, sep=", "):
                if isinstance(value, list):
                    return sep.join(str(v) for v in value)
                return "" if value is None else str(value)

            normalized = {
                "skills": as_text(pick("skills", default="")),
                "strongest_language": as_text(pick("strongest_language", "strongest_skill", default="")),
                "summary": pick("summary", "recruiter_style_summary", "recruiter_summary"),
            }

            if criteria or use_jd_score:
                raw_scores = record.get("criteria_scores") or record.get("criterion_scores") or []
                if not isinstance(raw_scores, list) or len(raw_scores) != len(criteria):
                    # Model didn't return one sub-score per criterion - can't
                    # compute a trustworthy weighted average from this, treat
                    # as a malformed generation and retry like the empty-result case.
                    if attempt < max_retries - 1:
                        print(f"criteria_scores length mismatch (got {len(raw_scores) if isinstance(raw_scores, list) else 'non-list'}, expected {len(criteria)}), retrying...")
                        time.sleep(2)
                        continue
                    else:
                        print("criteria_scores length mismatch, out of retries.")
                        return None

                if use_jd_score:
                    jd_raw = record.get("overall_jd_fit_score", record.get("jd_fit_score"))
                    if jd_raw is None:
                        if attempt < max_retries - 1:
                            print("overall_jd_fit_score missing while jd_weight > 0, retrying...")
                            time.sleep(2)
                            continue
                        else:
                            print("overall_jd_fit_score missing, out of retries.")
                            return None

                breakdown = []
                weighted_sum = 0.0
                weight_total = 0.0
                for c, item in zip(criteria, raw_scores):
                    try:
                        sub_score = max(0, min(100, int(round(float(item.get("score", 0))))))
                    except (TypeError, ValueError, AttributeError):
                        sub_score = 0
                    weight = float(c["weight"])
                    breakdown.append({"criterion": c["text"], "weight": weight, "score": sub_score})
                    weighted_sum += sub_score * weight
                    weight_total += weight

                if use_jd_score:
                    try:
                        jd_sub_score = max(0, min(100, int(round(float(jd_raw)))))
                    except (TypeError, ValueError):
                        jd_sub_score = 0
                    breakdown.append({"criterion": JD_LABEL, "weight": jd_weight, "score": jd_sub_score})
                    weighted_sum += jd_sub_score * jd_weight
                    weight_total += jd_weight

                normalized["score"] = int(round(weighted_sum / weight_total)) if weight_total > 0 else 0
                normalized["criteria_breakdown"] = breakdown
            else:
                # Normalize score to an int 0-100
                try:
                    normalized["score"] = max(0, min(100, int(round(float(record.get("score", 0))))))
                except (TypeError, ValueError):
                    normalized["score"] = 0

            # Occasionally the model returns a technically-valid but empty
            # JSON object (no exception, no error) - all fields blank and
            # score 0. That's indistinguishable from a real result unless we
            # check for it explicitly, and silently returning it would look
            # like a genuine "this candidate scored 0" judgment rather than
            # a malformed generation. Treat it as retryable, same as a
            # rate limit, rather than returning it as-is.
            is_empty_result = (
                not normalized["skills"]
                and not normalized["strongest_language"]
                and not normalized["summary"]
                and normalized["score"] == 0
            )
            if is_empty_result:
                if attempt < max_retries - 1:
                    print(f"Empty/malformed generation (attempt {attempt + 1}/{max_retries}), retrying...")
                    time.sleep(2)
                    continue
                else:
                    print("Empty/malformed generation, out of retries.")
                    return None

            return normalized

        except (RateLimitError, APIStatusError) as e:
            # Groq surfaces "tokens per minute" limits as either a 429
            # (RateLimitError) or a 413 (plain APIStatusError) depending on
            # whether the limit was hit before or after estimating the
            # request - both are the same underlying rate limit, so both
            # get the same retry/backoff treatment.
            status_code = getattr(e, "status_code", None)
            is_rate_limit = isinstance(e, RateLimitError) or status_code in (429, 413)

            if is_rate_limit and attempt < max_retries - 1:
                wait = retry_wait_seconds * (attempt + 1)
                print(f"Rate limited (status {status_code}), retrying in {wait}s (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(wait)
            elif is_rate_limit:
                print(f"Rate limited (status {status_code}), out of retries: {e}")
                return None
            else:
                print(f"API error in analyze_resume_for_sheet: {e}")
                return None

        except Exception as e:
            print(f"Error in analyze_resume_for_sheet: {str(e)}")
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