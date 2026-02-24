# GENERATE-EVAL-SCENARIOS (Skill-Based)

Generate evaluation scenarios that measure how useful and effective a skill is.  Together the scenarios will cover every line by line instruction in the skill, and provide evidence for whether it is followed when its relevant to do so.

Good scenarios will contain tasks where a general-purpose agent can produce *some* solution, but only some of the reasonable solutions will follow the instructions of the skill. E.g. if the skill says to use a particular library, the task won't proscribe the library but the criteria will.

The scenarios will be used in an eval harness with the following constraints:
1. An agent will be given the scenario and either the skill or no skill, and asked to solve the skill.
2. No other environment set up will be carried out.  The agent will not have access to additional input files, API keys, special accounts or proprietary software.  They will have network access.
3. The agent should be able to finish the task within 10 mins to avoid a time out.
4. The agent will not be able to interact with a user.
4. The files left in the workspace at the end will be sent to an LLM to grade.  No large files should be left in the workspace -- the agent should be asked to clean up any large files it downloaded (>50MB), and it should avoid generating very large files if possible.
5. Only the files will be available for grading --> no agent logs or session transcripts will be available to the grader -- this means that the workflow or tools used by the agent will only be visible to the grader if the agent is asked to make a log of them or script its behavior in some way.

## Configuration

- Scenario count: 5


## Task 1: Research the Skill

Read **`SKILL.md`** thoroughly — this is the entry point. Then explore the rest of the skill folder, including subfolders like `references/` and `scripts/`. Files referenced from SKILL.md often hold the most specific guidance.

Extract every **instruction** in the skill, that directs an agent to do or not do a specific thing:
- Use specific libraries or methods
- Use scripts to achieve specific outcomes
- Set magic numbers, or specific syntax choices
- Leverage proprietary APIs, specialised language or follow internal patterns
- Avoid certain gotchas, obey warnings and prohibitions

Write a file called "instructions.json", including all the instructions you've found:
```json
{
  "instructions" : [
    {
      "instruction": "<instruction from the skill>",
      "original_snippets": "<substring from the original text, including context.  Separate with ...>",
      "relevant_when": "<description of type of scenario where this would kick in",
      "why_given": "<reminder|new knowledge|particular prefence>"
    }
  ]
}
```
For relevant_when, describe the type of scenarios that would make this instruction relevant (e.g. when writing type script code, when setting up a new database etc).
For why_given, give your best guess for why the skill writer included this instruction -- is it a simple reminder to the agent of something it might know, is it new knowledge that the agent may not know, or is it expressing a preference among many options?

## Task 2: Plan Scenarios

Plan 5 scenario ideas before writing any files. Group the instructions to design scenarios that will cover as many of the instructions as possible, by setting up conditions that match the "relevant_when" cases.  
1. Each scenario should make sense with a cohesive task for the agent to do, and a list of criteria that observe whether certain instructions were followed as it performed them.
2. Between them the scenarios should cover as many of the instructions as possible, preferring those that express "preferences" and "new knowledge" and then "reminders" in that order.  
3. Each criteria must be feasible to grade -- this means that the task should leave enough evidence for the criteria to be assessed.  If the instruction is to follow a workflow, then consider asking the agent to script the workflow, or document a plan, or create another specific artifact that can be graded. 
4. Tasks should be designed to be **feasible** given the limitations of the eval system -- if there is no way to do this given the nature of the dependencies needed, then the scenario should be marked as infeasible.
   -- Do NOT create a folder for infeasible scenarios. Record them in `summary_infeasible.json` instead.
5. Good scenarios should:
   -- **be realistic** real world tasks that a user may ask for
   -- **not contain the instructions** that are being tested - but instead instruct something higher level so that they discriminate between the agent following the skill and not.   E.g. if the instruction enumerates files to be made during initialisation, then the task wouldn't enumerate the files, but will just ask for initialisation.


## Task 3: Generate Each Scenario

For each feasible scenario, create `scenario-{idx}` (0-indexed: `scenario-0`, `scenario-1`, ...) with three files.

### 3a. `capability.txt`

A couple-word summary of the instructions being tested (e.g. "Correct directory structure") or the type of task being done.  

### 3b. `criteria.json` 

The checklist that will be used to evaluate the final artifacts from the solution.  
- Items in the checklist should be derived by the instructions being tested. 
  - DO TEST skill specific instructions
  - DON'T test general software engineering practises that aren't specifically instructed in the skill.
  - DON'T test for the general quality of the task outputs (e.g. that files are created, that task instructions are followed)
  - **For every criteria it should be possible to point to the instruction it is testing**
- Items should be a precise, testable checklist of elements that a grader can check for.  
- Pick binary criteria that will be easy to check yes/no to, requiring as little discernment as possible, but capturing the heart of the instruction -- focussing on objective measures where possible. 
- Break apart any complex instructions into individual simple criteria -- (e.g. split apart "uses correct package and correct model")
- Don't add checklist items that just verify that the task completed, or that there was general success -- **focus on whether the skill instructions were followed**.
- Criteria can be positive or negative (e.g. "use library X", "don't use pattern Y") - mirror what is stated in the instruction.
- Prefer to score all elements equally, downweight items that are repeated in multiple scenarios.

```json
{
  "context": "<2-3 sentence overview>",
  "type": "weighted_checklist",
  "checklist": [
    {
      "name": "<short name (1-4 words)>",
      "description": "<what is being evaluated — keep conceptual, not exact names>",
      "max_score": "<number>"
    }
  ]
}
```

**Writing binary criteria:**

| Avoid (causes partial credit) | Use instead (binary) |
|-------------------------------|----------------------|
| "Repeatedly emphasizes X" | "Contains at least 3 of: 'term1', 'term2', 'term3'" |
| "Uses non-standard layout" | "Uses at least ONE of: asymmetric grid, overlapping elements, rotated content" |
| Subjective: "clear", "creative" | Presence checks: "Includes X", "Does NOT use Y" |



**example**

```json
{
  "context": "Tests whether the agent uses the composition plan workflow for fine-grained music control, handles mutually exclusive parameters correctly, and avoids deprecated packages.",
  "type": "weighted_checklist",
  "checklist": [
    {
      "name": "Correct client package",
      "description": "Uses the @elevenlabs/elevenlabs-js, not the deprecated elevenlabs package",
      "max_score": 10
    },
    {
      "name": "Composition plan generation",
      "description": "Uses music.composition_plan.create() followed by music.compose() to generate a composition plan",
      "max_score": 10
    },
    {
      "name": "Mutually exclusive params",
      "description": "Does NOT pass both prompt and composition_plan to compose() — uses one or the other",
      "max_score": 10
    },
    ... // other rubrics directly testing what the skill suggests
  ]
}
```
(Abbreviated — real rubrics will likely have 10-12 items summing to 100.)

### 3c. `task.md`

Describes a realistic problem that *naturally requires* that the skill instructions are relevant — but without revealing the instructions or hinting at them strongly. Make it so a competant agent could solve it in ways that the skill didn't specify.  Make it challenging and interesting rather than testing what's obvious.

```markdown
# [Task Title]

## Problem/Feature Description

[1-2 paragraphs. Construct a believable business scenario around the skill
instructions being tested. Explain who needs this, what problem or gap exists,
what's already available. The scenario should make the skill's guidance
relevant and necessary. Write as a story, not a list of constraints.]

## Output Specification

[Give details on what should be produced.
If you ask the agent to produce a script to automate doing the task or to produce a log of the process, include those files as an output as well.
Name the expected output files and formats, unless these are part of the instructions and will give away the criteria.]

## Input Files (optional)

[Provide inlined input files that can create a starting state to work on if necessary , e.g. files before an edit.  
These **must be fully generated** when the task file is written, no additional files will be available at run time.
Do not describe files to be provided later, DO NOT mention that this is an eval]

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/example.txt ===============
[file contents]
```

**The task must be self-contained and actionable.** An agent should be able to read the task and immediately start working using only the task description plus the skill (or their own knowledge). If the task is too vague to act on, add more context — but focus on the problem, not the solution.

**The task should not have a large number of prerequisites or leave large files.**
- Avoid requiring the agent to download very large files (>100MB) or to install and set up a complex environment before starting.  Mark the scenario as infeasible if this is unavoidable.

**Good vs bad tasks:**
Don't hint too heavily at the solution or give away details that will make it easy to pass.

| Skill Instruction | Good Task (problem-framed) | Bad Task (instruction-framed) |
|---|---|---|
| Use Batch API | "The ops team needs to migrate 500 users to a new email domain after a company rebrand" | "Update users using batch API" |
| Create A, B and C for each service | "Set up the initial cloud infrastructure for a new microservice" | "Create files A, B and C" |
| Use input validation | "Set up the form to collect user information" | "Add validation: name (string) and phone number (number)" |
| Use a valid model (one of X, Y and Z) | "The customer asks you to pick a reasonable configuration" | "The customer wants to use model X, and is based in region A" |



## Task 4: Validate and refine

Check for instruction leakage in each scenario:

- [ ] For each item in criteria.json check it is not also written into task.md. If found, rewrite the task to remove the hint. The agent solving the task should discover HOW to implement it from the skill or their own knowledge — not from the task description.  
     -  E.g. the task should ask NOT for a specific file to be written IF the criteria check that file is there.

Check for eval feasibility

- [ ] No suggestion that extra files, set up or config will be provided later.  In particular, if there are input files, they are already inlined into the task.md.  Scenarios are marked infeasible if they can't be run without extra files.


Run these checks across all scenarios:

- [ ] Scenario folders numbered sequentially (no gaps)
- [ ] Each folder has: `capability.txt`, `task.md`, `criteria.json`
- [ ] Each criteria.json sums to exactly 100
- [ ] Each criteria.json ideally has 10+ checklist items, testing many of the instructions from the skill

Finally:
- [ ] Make sure that no scenario mentions that this is an eval, or a simulated excerise or that its not real.  Just ask for the task to be completed!
 

## Task 5: Create Summary Files


**summary.json**:
```json
{
  "total_scenarios": <number>,
  "instructions_coverage": {
    "total_instructions": <from instructions.json>,
    "instructions_tested": <unique instructions within scenarios>,
    "coverage_percentage": <percentage>
  },
  "reason_distribution": {
    "reminder": "<count>",
    "new knowledge": "<count>",
    "preference": "<count>"
  }
}
```

**summary_infeasible.json**:
```json
{
  "total_infeasible": <number>,
  "infeasible_scenarios": [
    {
      "scenarios": "<scenarios name>",
      "reasoning": "<why this cannot be evaluated>"
    }
  ]
}
```
