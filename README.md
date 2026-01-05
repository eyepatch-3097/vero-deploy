# Vero

**Vero** is an AI-powered content workspace for founders, marketers, and operators to **plan, generate, refine, and publish high-quality written content** (blogs, LinkedIn posts, etc.) with speed and consistency — without juggling multiple tools.

It combines **content generation, iteration, image creation, and credit-based usage** into one clean workflow.

---

## What Vero Can Do

### 1. Content Generation
- Generate **blogs** and **LinkedIn posts** from a topic or idea
- Supports structured, long-form writing (not just short prompts)
- Optimized for clarity, tone, and real-world publishing use cases

### 2. Content Iteration (Improve Mode)
- Improve existing drafts instead of regenerating from scratch
- Control:
  - Length (short / medium / long)
  - Tone (as-is, more casual, more formal)
  - Optional examples or data
- Every improvement creates a **new version**, preserving history

### 3. Topic Change Without Losing Context
- Change the topic/title of an existing draft
- AI reworks the content while maintaining intent and structure
- Useful for repositioning content without starting over

### 4. Content History & Versioning
- Every generated or modified piece is stored
- View:
  - Drafts
  - Approved content
  - Full version history
- Revisit, iterate, or publish later

### 5. AI Hero Image Generation
- Generate a **custom hero image** for each blog or post
- Flow:
  1. AI analyzes the content
  2. Creates a focused visual prompt
  3. Generates a high-quality image
- Images are stored and served from persistent storage
- Costs credits (transparent and predictable)

### 6. Image Discovery (Pexels)
- Automatically suggests image search ideas based on content
- Fetches relevant image options for inspiration or fallback usage
- Image search terms are generated once and reused (not regenerated on every view)

### 7. Credits Wallet
- Credit-based usage model
- Clear visibility into:
  - Current balance
  - Usage history
  - Actions that consume credits (generate, improve, images)

---

## How Vero Works (High Level)

1. **User creates content**  
   Topic → AI generates a draft

2. **User iterates**  
   Improve, change topic, or refine tone  
   Each action creates a new version

3. **Enhance visually**  
   Generate an AI hero image or pick from suggested image ideas

4. **Approve & publish**  
   Final version is marked approved and ready for publishing elsewhere

---

## Tech Overview

- **Backend**: Django
- **Frontend**: Server-rendered Django templates + minimal JS
- **AI**:
  - OpenAI (text + image generation)
- **Storage**:
  - Persistent disk for generated images
- **Auth**:
  - Email + password authentication
- **Deployment**:
  - Render (Gunicorn + persistent disk)

---

## Key Design Principles

- **Iteration over regeneration**  
  Improve existing drafts instead of rewriting everything

- **Minimal UI, maximum focus**  
  Clean layouts designed for reading and editing, not dashboards

- **Predictable AI usage**  
  Credit-based system keeps costs transparent

- **Single source of truth**  
  One place for drafts, images, versions, and history

---

## Who Vero Is For

- Founders writing regularly but short on time
- Marketers who need structured, repeatable content
- Operators building content pipelines without CMS complexity
- Anyone who wants **AI-assisted writing without losing control**

---

## Status

Vero is under active development.  
New capabilities are being added around:
- Publishing workflows
- Content calendars
- Multi-channel distribution
- Style memory & personalization

---

**Vero** helps you think less about *how to write* and more about *what to say*.
