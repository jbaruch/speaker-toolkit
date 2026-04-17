# Robocoders: Judgment Day
**Spec:** Keynote | 45 min | DevNexus 2026
**Slide budget:** 60 slides

## Illustration Style Anchor
**Model:** `gemini-3-pro-image-preview`
### STYLE ANCHOR (FULL — Landscape 1920x1080)
> Retro sci-fi propaganda poster aesthetic. Bold colors, dramatic lighting.

## Opening Sequence [3 min, slides 1-5]
### Slide 1: Title Slide
- Format: **FULL**
- Illustration: Retro robot at a desk
- Image prompt: `[STYLE ANCHOR]. A retro robot sitting at a coding desk.`
- Visual: Full-bleed title card
- Speaker: Welcome everyone.

### Slide 2: The Promise
- Visual: Text slide with bold claim
- Speaker: Every vendor promises that AI will write all your code. But let's look at what https://github.com/features/copilot actually delivers versus the marketing. Check the research at https://arxiv.org/abs/2302.06590 for the real numbers.

### Slide 3: Shownotes
- Visual: QR code + URL
- Speaker: You can find all resources at https://jbaru.ch/2026-04-16-devnexus-robocoders-judgment-day

### Slide 4: About Me
- Visual: Bio slide with photo
- Speaker: I'm Baruch, DevOps advocate at JFrog. Find me at https://twitter.com/jbaruch

## Act 1: The Reality Check [12 min, slides 5-20]
### Slide 5: The Benchmark Trap
- Visual: Chart showing benchmark vs real-world performance
- Speaker: The SWE-bench results from https://github.com/princeton-nlp/SWE-bench look impressive, but real codebases tell a different story. As discussed in RFC 9421 on HTTP message signatures, even basic protocol work needs human judgment.

### Slide 6: Code Review Matters
- Visual: Screenshot of a PR review
- Speaker: Tools like `SonarQube` and `CodeClimate` catch surface issues, but architectural decisions need human expertise. The OWASP Top 10 at https://owasp.org/Top10/ hasn't changed because AI can't reason about security context.

### Slide 7: The Human Element
- Visual: Diagram of human-AI collaboration
- Speaker: *"Accelerate: Building and Scaling High Performing Technology Organizations"* by Nicole Forsgren proves that team dynamics, not tools, predict delivery performance. Also see RFC 7519 for JWT specifics.

```python
# This URL should NOT be extracted: https://example.com/api/v1/not-a-resource
def authenticate():
    pass
```

### Slide 8: Demo Setup
- Format: **FULL**
- Illustration: Terminal with code
- Image prompt: `[STYLE ANCHOR]. A dramatic terminal screen showing code diffs. https://not-a-resource.example.com/should/be/ignored`
- Visual: Live demo of AI pair programming with `Cursor` IDE
- Speaker: Let me show you how `Cursor` and `GitHub Copilot` handle a real refactoring task. We'll use `Kubernetes` manifests as our test case.

### Slide 12: Metrics That Matter
- Visual: Dashboard
- Speaker: Track your AI adoption with proper metrics. The DORA framework at https://dora.dev is the gold standard. Don't forget https://dora.dev mentioned earlier — it's that important.

## Act 2: Judgment [15 min, slides 21-40]
### Slide 21: The Decision Framework
- Visual: Decision tree
- Speaker: When should you use AI for code? Let's build a framework. Check https://github.com/jbaruch/ai-coding-guidelines for our open-source decision tree.

### Slide 30: Enterprise Reality
- Visual: Org chart with AI integration points
- Speaker: Enterprise adoption of `Terraform` and `Ansible` for IaC shows that automation succeeds when humans set the guardrails. See https://github.com/hashicorp/terraform for the reference implementation.

## Closing Sequence [3 min, slides 55-60]
### Slide 55: Summary
- Visual: Three key takeaways
- Speaker: Remember — AI is a tool, not a replacement. The judgment is yours.

### Slide 58: Coda — Further Reading
- Visual: Resource list
- Speaker: For deeper dives: *"The Pragmatic Programmer"* by Dave Thomas covers the fundamentals. Check out https://github.com/google/eng-practices for Google's engineering practices. Also see RFC 2119 for how standards define requirement levels — relevant to how we should define AI coding standards.

### Slide 60: Thank You
- Visual: Contact info
- Speaker: Find me at @jbaruch. Shownotes at https://jbaru.ch/2026-04-16-devnexus-robocoders-judgment-day
