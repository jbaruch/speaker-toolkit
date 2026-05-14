# Generate a Speaker Profile from a Completed Vault

## Background

Taylor Okonkwo is a security researcher and conference speaker who has been building a rhetoric knowledge vault over the past year. They recently completed their 12th talk analysis and their first clarification session with the vault assistant. Now that the vault has reached the threshold for profile generation, it's time to generate a comprehensive `speaker-profile.json` that the presentation-creator can use for future talks.

The vault is located at `./vault/` and all the data is provided below. Your job is to generate the speaker profile from this vault data and save it to `./vault/speaker-profile.json`.

## Output Specification

Generate `vault/speaker-profile.json` — a complete speaker profile synthesizing all available vault data.

The profile should capture Taylor's patterns, defaults, and infrastructure in a structured form that another tool can consume programmatically. Include speaker badges that reflect Taylor's specific talk history.

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/vault/tracking-database.json ===============
{
  "config": {
    "vault_root": "./vault",
    "talks_source_dir": "./talks",
    "pptx_source_dir": "./presentations",
    "python_path": "./vault/.venv/bin/python3",
    "template_skip_patterns": ["template"],
    "speaker_name": "Taylor Okonkwo",
    "speaker_handle": "@t_okonkwo",
    "speaker_website": "taylorsec.io",
    "shownotes_url_pattern": "speaking.taylorsec.io/{slug}",
    "template_pptx_path": "./presentations/template/taylorsec-template.pptx",
    "presentation_file_convention": "./presentations/{conference}/{year}/{talk-slug}/",
    "clarification_sessions_completed": 1,
    "publishing_process": {
      "export_format": "pdf_and_pptx",
      "export_method": "libreoffice --headless --convert-to pdf",
      "shownotes_publishing": {
        "enabled": true,
        "method": "push to taylorsec.io/speaking git repo"
      },
      "qr_code": {
        "enabled": true,
        "target": "shownotes_url",
        "insert_into_deck": true,
        "slide_position": "shownotes_slide"
      }
    }
  },
  "talks": [
    {
      "filename": "2023-06-blackhat-supply-chain.md",
      "title": "Software Supply Chain: The Attack You're Not Watching",
      "conference": "Black Hat USA", "date": "2023-06-14",
      "status": "processed", "processed_date": "2024-01-10",
      "structured_data": {
        "slide_count": 62, "talk_duration_estimate": "45 min",
        "opening_type": "failure_framing", "closing_type": "summary_cta",
        "narrative_arc_type": "problem_diagnosis_solution",
        "audience_interaction_count": 3, "meme_count": 8, "image_only_slide_count": 14
      },
      "pattern_observations": {
        "pattern_ids": ["narrative-arc", "bookends", "brain-breaks", "foreshadowing", "expansion-joints"],
        "antipattern_ids": [],
        "pattern_score": 5
      }
    },
    {
      "filename": "2023-09-owasp-dependency-risks.md",
      "title": "Dependency Risks in the Modern Stack",
      "conference": "OWASP AppSec EU", "date": "2023-09-05",
      "status": "processed", "processed_date": "2024-01-10",
      "structured_data": {
        "slide_count": 55, "talk_duration_estimate": "40 min",
        "opening_type": "bold_claim", "closing_type": "summary_cta",
        "narrative_arc_type": "problem_diagnosis_solution",
        "audience_interaction_count": 2, "meme_count": 6, "image_only_slide_count": 10
      },
      "pattern_observations": {
        "pattern_ids": ["narrative-arc", "bookends", "brain-breaks", "foreshadowing"],
        "antipattern_ids": ["shortchanged"],
        "pattern_score": 3
      }
    },
    {
      "filename": "2023-11-devopdays-sbom.md",
      "title": "SBOMs Are Not Enough",
      "conference": "DevOpsDays Amsterdam", "date": "2023-11-20",
      "status": "processed", "processed_date": "2024-01-10",
      "structured_data": {
        "slide_count": 48, "talk_duration_estimate": "30 min",
        "opening_type": "failure_framing", "closing_type": "callback",
        "narrative_arc_type": "problem_diagnosis_solution",
        "audience_interaction_count": 4, "meme_count": 7, "image_only_slide_count": 11
      },
      "pattern_observations": {
        "pattern_ids": ["narrative-arc", "bookends", "brain-breaks", "backtracking", "expansion-joints"],
        "antipattern_ids": [],
        "pattern_score": 5
      }
    },
    {
      "filename": "2024-02-rsaconf-zero-trust.md",
      "title": "Zero Trust Is Not A Product",
      "conference": "RSA Conference", "date": "2024-02-26",
      "status": "processed", "processed_date": "2024-03-01",
      "structured_data": {
        "slide_count": 70, "talk_duration_estimate": "45 min",
        "opening_type": "bold_claim", "closing_type": "summary_cta",
        "narrative_arc_type": "problem_diagnosis_solution",
        "audience_interaction_count": 2, "meme_count": 10, "image_only_slide_count": 18
      },
      "pattern_observations": {
        "pattern_ids": ["narrative-arc", "bookends", "brain-breaks", "foreshadowing", "live-demo"],
        "antipattern_ids": ["shortchanged"],
        "pattern_score": 4
      }
    },
    {
      "filename": "2024-04-kubecon-runtime-security.md",
      "title": "Runtime Security in Kubernetes: What Actually Works",
      "conference": "KubeCon EU", "date": "2024-04-18",
      "status": "processed", "processed_date": "2024-05-01",
      "structured_data": {
        "slide_count": 58, "talk_duration_estimate": "45 min",
        "opening_type": "failure_framing", "closing_type": "summary_cta",
        "narrative_arc_type": "problem_diagnosis_solution",
        "audience_interaction_count": 3, "meme_count": 9, "image_only_slide_count": 15
      },
      "pattern_observations": {
        "pattern_ids": ["narrative-arc", "bookends", "brain-breaks", "foreshadowing", "a-la-carte-content"],
        "antipattern_ids": [],
        "pattern_score": 5
      }
    },
    {
      "filename": "2024-05-gotosec-threat-model.md",
      "title": "Threat Modeling for Teams That Hate Threat Modeling",
      "conference": "GOTO Security", "date": "2024-05-10",
      "status": "processed", "processed_date": "2024-05-20",
      "structured_data": {
        "slide_count": 52, "talk_duration_estimate": "45 min",
        "opening_type": "audience_poll", "closing_type": "summary_cta",
        "narrative_arc_type": "problem_diagnosis_solution",
        "audience_interaction_count": 5, "meme_count": 8, "image_only_slide_count": 12
      },
      "pattern_observations": {
        "pattern_ids": ["narrative-arc", "bookends", "brain-breaks", "foreshadowing", "backtracking"],
        "antipattern_ids": [],
        "pattern_score": 5
      }
    },
    {
      "filename": "2024-07-defcon-llm-attacks.md",
      "title": "LLM Attack Surfaces: A Threat Taxonomy",
      "conference": "DEF CON", "date": "2024-07-26",
      "status": "processed", "processed_date": "2024-08-05",
      "structured_data": {
        "slide_count": 65, "talk_duration_estimate": "50 min",
        "opening_type": "bold_claim", "closing_type": "summary_cta",
        "narrative_arc_type": "problem_diagnosis_solution",
        "audience_interaction_count": 2, "meme_count": 12, "image_only_slide_count": 20
      },
      "pattern_observations": {
        "pattern_ids": ["narrative-arc", "bookends", "brain-breaks", "foreshadowing", "live-demo"],
        "antipattern_ids": ["bullet-riddled-corpse"],
        "pattern_score": 4
      }
    },
    {
      "filename": "2024-09-allday-devops-sast.md",
      "title": "SAST That Doesn't Make Your Dev Team Hate You",
      "conference": "All Day DevOps", "date": "2024-09-18",
      "status": "processed", "processed_date": "2024-09-25",
      "structured_data": {
        "slide_count": 45, "talk_duration_estimate": "30 min",
        "opening_type": "failure_framing", "closing_type": "callback",
        "narrative_arc_type": "problem_diagnosis_solution",
        "audience_interaction_count": 3, "meme_count": 6, "image_only_slide_count": 9
      },
      "pattern_observations": {
        "pattern_ids": ["narrative-arc", "bookends", "brain-breaks", "expansion-joints"],
        "antipattern_ids": [],
        "pattern_score": 4
      }
    },
    {
      "filename": "2024-10-owasp-appsec-ai.md",
      "title": "Securing AI: What OWASP Top 10 for LLMs Gets Right (and Wrong)",
      "conference": "OWASP AppSec USA", "date": "2024-10-15",
      "status": "processed", "processed_date": "2024-10-22",
      "structured_data": {
        "slide_count": 60, "talk_duration_estimate": "45 min",
        "opening_type": "failure_framing", "closing_type": "summary_cta",
        "narrative_arc_type": "problem_diagnosis_solution",
        "audience_interaction_count": 3, "meme_count": 9, "image_only_slide_count": 14
      },
      "pattern_observations": {
        "pattern_ids": ["narrative-arc", "bookends", "brain-breaks", "foreshadowing", "backtracking"],
        "antipattern_ids": [],
        "pattern_score": 5
      }
    },
    {
      "filename": "2024-11-kubecon-na-policy.md",
      "title": "Policy as Code: Beyond the Basics",
      "conference": "KubeCon NA", "date": "2024-11-13",
      "status": "processed", "processed_date": "2024-11-20",
      "structured_data": {
        "slide_count": 55, "talk_duration_estimate": "45 min",
        "opening_type": "bold_claim", "closing_type": "summary_cta",
        "narrative_arc_type": "problem_diagnosis_solution",
        "audience_interaction_count": 2, "meme_count": 7, "image_only_slide_count": 11
      },
      "pattern_observations": {
        "pattern_ids": ["narrative-arc", "bookends", "brain-breaks", "foreshadowing", "a-la-carte-content"],
        "antipattern_ids": [],
        "pattern_score": 5
      }
    },
    {
      "filename": "2025-01-fosdem-sbom-v2.md",
      "title": "SBOMs in 2025: Lessons From Two Years in the Field",
      "conference": "FOSDEM", "date": "2025-01-31",
      "status": "processed", "processed_date": "2025-02-05",
      "structured_data": {
        "slide_count": 42, "talk_duration_estimate": "25 min",
        "opening_type": "failure_framing", "closing_type": "callback",
        "narrative_arc_type": "problem_diagnosis_solution",
        "audience_interaction_count": 3, "meme_count": 5, "image_only_slide_count": 8
      },
      "pattern_observations": {
        "pattern_ids": ["narrative-arc", "bookends", "brain-breaks", "backtracking"],
        "antipattern_ids": [],
        "pattern_score": 4
      }
    },
    {
      "filename": "2025-02-rsaconf-devsecops.md",
      "title": "DevSecOps Patterns That Actually Scale",
      "conference": "RSA Conference", "date": "2025-02-24",
      "status": "processed", "processed_date": "2025-03-01",
      "structured_data": {
        "slide_count": 58, "talk_duration_estimate": "45 min",
        "opening_type": "failure_framing", "closing_type": "summary_cta",
        "narrative_arc_type": "problem_diagnosis_solution",
        "audience_interaction_count": 3, "meme_count": 9, "image_only_slide_count": 15
      },
      "pattern_observations": {
        "pattern_ids": ["narrative-arc", "bookends", "brain-breaks", "foreshadowing", "expansion-joints"],
        "antipattern_ids": [],
        "pattern_score": 5
      }
    }
  ],
  "confirmed_intents": [
    {
      "pattern": "delayed_intro",
      "intent": "deliberate",
      "rule": "Do not open with a traditional bio slide — go straight to content or a hook. Bio appears at slide 3 at the earliest.",
      "note": "Taylor confirmed: audiences have already seen the session title and bio in the schedule. Get into the content first."
    },
    {
      "pattern": "failure_framing_open",
      "intent": "deliberate",
      "rule": "Prefer opening with a real failure story (anonymized) to build audience empathy before presenting solutions",
      "note": "Taylor confirmed: 'I find audiences trust me more if I show I've seen things go wrong before I tell them how to fix things.'"
    }
  ]
}

=============== FILE: inputs/vault/rhetoric-style-summary.md ===============
# Rhetoric & Style Summary — Taylor Okonkwo
Last updated: 2025-03-01 | 12 talks analyzed

## Status
Processed: 12 | Skipped: 0 | Languages: en (12) | Co-presenters: 0

## Section 1: Opening Pattern
Taylor consistently opens with either a failure story (7/12) or a bold claim (4/12). Deliberately delays self-introduction to slide 3. No audience poll openings until 2024, where one was used (Threat Modeling talk).

## Section 2: Narrative Structure
Every talk uses a problem-diagnosis-solution arc (12/12). Three-act structure is highly consistent. Taylor uses explicit mid-talk pivots ("But here's what this misses..."). Bookends present in 11/12 talks — opening scenario resolves in the closing.

## Section 3: Humor & Wit
Dry, deadpan. Humor placed after a serious point, not before — used as release valve. Security-adjacent jokes (threat actors, CVEs) that resonate with technical audiences. Avoids slapstick and pop-culture outside of security community norms.

## Section 4: Audience Interaction
Show-of-hands in every talk (avg 3 per talk). Rhetorical questions used at section transitions. No polling tools used.

## Section 5: Transition Techniques
Explicit verbal bridges. Frequent foreshadowing: "I'll come back to this" (observed in 10/12 talks). Some backtracking: "Remember that supply chain example from the opening."

## Section 6: Closing Pattern
Consistent three-part close: summary → specific CTA → shownotes URL (11/12). Callback close present in 4/12 (DevOpsDays, FOSDEM, All Day DevOps, Threat Modeling talks).

## Section 7: Verbal Signatures
- "The attack surface you're not watching"
- "And this is where it gets interesting" (transition phrase)
- "I'll show you the actual CVE" (credibility anchor)
- "Let me be specific here" (before data)

## Section 12: Pacing Clues
Average slide count: 56. WPM estimate: 148-162 (from transcript length vs duration). Always includes modular cut lines. Consistently runs 1.3-1.4 slides/minute.

## Section 15: Areas for Improvement
- Shortchanged: 2 talks showed time compression in Act 3. Expansion joints help.
- Bullet-Riddled Corpse: 1 talk (DEF CON LLM). High-content talk under time pressure.

## Section 16: Speaker-Confirmed Intent
- Delayed intro: deliberate — audiences have seen the schedule bio, dive into content first
- Failure framing: deliberate — builds trust before presenting solutions
