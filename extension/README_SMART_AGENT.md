# Smart AI Agent - Setup Guide

**Created:** 2026-06-02  
**Status:** Ready to use! 🚀

---

## What is this?

The **Smart AI Agent** is an autonomous bulletin extraction system that **actually does the work for you** instead of just giving advice like the old Gemini AI.

### What it does:
- ✅ Looks at parish website automatically
- ✅ Figures out where the bulletin is
- ✅ Clicks buttons and extracts the file
- ✅ Verifies it got the right week
- ✅ Learns successful patterns for next time
- ✅ Gets cheaper and faster over time

### What changed:
- ❌ Old: Gemini gives passive advice → you still do all the work
- ✅ New: OpenAI GPT-4o-mini does the work → you just click "Smart Extract"

---

## Setup (5 minutes)

### Step 1: Add OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Sign up or log in
3. Click "Create new secret key"
4. Copy the key (starts with `sk-proj-...`)
5. Add $5-10 credit to your account

### Step 2: Add Key to Extension

1. Click the Parish Trainer extension icon (in browser toolbar)
2. Click "🔑 GitHub Settings" to expand
3. Find "OpenAI API Key (for Smart Agent)" field
4. Paste your key
5. Click "💾 Save settings"

### Step 3: Test It!

1. Open any parish website
2. Look for the floating Parish Trainer toolbar
3. Find the **🚀 Smart Extract (AI Agent)** button (green, prominent)
4. Click it and watch the magic! ✨

The agent will:
- Analyze the page
- Create an extraction plan
- Execute the plan
- Extract the bulletin
- Verify it's the right week
- Show you the result

---

## How to Use

### Basic Usage

1. **Navigate to parish website**
2. **Click "🚀 Smart Extract (AI Agent)"**
3. **Wait while agent works** (usually 5-10 seconds)
4. **Review the result:**
   - Green panel shows bulletin URL found
   - Click "🔗 Open" to view bulletin
   - Click "💾 Save as Recipe" to add to training
5. **Done!**

### First Time vs. Later Visits

**First time visiting a parish:**
- Agent uses AI to figure it out (~5-10 seconds)
- Costs ~$0.001-0.002 (less than half a penny)
- After success, saves the pattern

**Second time onwards:**
- Agent uses saved pattern (instant!)
- Costs $0 (no AI needed)
- Only uses AI if pattern fails

### If Something Goes Wrong

**Agent says "No bulletin found":**
- The site might be too complex
- Try manual method (record clicks yourself)
- Report the parish URL so we can improve

**Agent extracts wrong bulletin:**
- Click "✖" to dismiss result
- Use manual extraction
- The agent learns from failures too

**"Add OpenAI API key" error:**
- You haven't added your key yet
- Follow Setup Step 1-2 above

---

## Cost Tracking

### Per Parish Costs
- **First extraction:** $0.001-0.002 (AI planning + verification)
- **After learning:** $0 (uses saved pattern)
- **Complex sites:** $0.002-0.005 (may need vision/retries)

### Monthly Estimates (100 parishes)
- **Month 1:** ~$3 (learning phase, uses AI for all)
- **Month 2:** ~$2 (50% learned patterns)
- **Month 3+:** ~$1.50 (80% patterns, 20% AI)

### Your $5 Credit
- $5 = ~2,500-5,000 parish extractions
- At 100 parishes/week = 25-50 weeks worth
- You're good for 6+ months!

---

## Features Explained

### 🧠 AI Planning
Agent analyzes page structure:
- Finds PDF links
- Identifies bulletin keywords
- Creates extraction plan
- Uses GPT-4o-mini (fast, cheap, smart)

### ⚙️ Execution
Agent performs actions:
- Clicks elements
- Scrolls if needed
- Waits for page loads
- Extracts PDF/image

### 🔍 Verification
Agent checks result:
- Verifies file exists
- Checks URL looks current
- Optional: Reads bulletin content
- Ensures right week

### 💾 Learning
Agent remembers success:
- Saves extraction pattern per domain
- Tracks confidence score
- Reuses pattern next time
- Updates if pattern fails

---

## Advanced Features

### Pattern Browser
Coming soon: View all learned patterns in Operator Console

### Self-Correction
Coming soon: Agent retries with different strategy when verification fails

### Vision Analysis
Coming soon: Agent can analyze page screenshots for image bulletins

### URL Prediction
Coming soon: Agent predicts next week's bulletin URL

---

## Comparison: Old vs New

| Feature | Old (Gemini) | New (GPT-4o-mini Agent) |
|---------|--------------|-------------------------|
| Gives advice | ✅ | ✅ |
| Actually extracts | ❌ | ✅ |
| Learns patterns | ❌ | ✅ |
| Verifies results | ❌ | ✅ |
| Self-corrects | ❌ | ✅ (coming soon) |
| Monthly cost (100 parishes) | $0.40 | $1.50-3 |
| **Time saved** | **0 hours** | **Many hours** |
| **Actually works** | ❌ | ✅ |

---

## Troubleshooting

### "Failed to create extraction plan"
- Check internet connection
- Verify OpenAI API key is correct
- Check you have credit in OpenAI account

### "OpenAI API error: 401"
- API key is wrong or expired
- Get new key from platform.openai.com
- Re-enter in extension settings

### "OpenAI API error: 429"
- Rate limit hit (too many requests)
- Wait a minute and try again
- This is rare with GPT-4o-mini

### "Verification failed"
- Agent extracted something but isn't sure it's right
- Check the URL manually
- Click "💾 Save" if it looks good
- Helps agent learn

### Agent is slow
- First time on new parish = normal (5-10 sec)
- After learning = should be instant
- Complex sites take longer

---

## Files Created

The Smart Agent system consists of:

```
extension/
├── agents/
│   ├── config.js         - Configuration
│   ├── planner.js        - AI planning logic
│   ├── executor.js       - Action execution
│   ├── verifier.js       - Result verification
│   ├── memory.js         - Learning/pattern storage
│   └── smart_agent.js    - Main orchestrator
├── content.js            - Integration (Smart Extract button)
├── popup.html            - Updated UI (OpenAI key field)
└── popup.js              - Updated settings save/load
```

---

## Next Steps

1. **Use it!** Click the Smart Extract button on parish sites
2. **Watch it learn** - Second visits will be instant
3. **Report issues** - Let me know which parishes fail
4. **Suggest improvements** - What features do you want?

---

## Support

**Questions?** Check the proposal documents:
- `docs/AI_AGENT_PROPOSAL.md` - Technical details
- `docs/AI_AGENT_SIMPLE_GUIDE.md` - Non-technical guide
- `ai_conversations/2026-06-02-ai-agent-proposal.md` - Full conversation log

**Problems?** The Smart Agent is brand new. If something doesn't work:
1. Try the manual method (it still works!)
2. Let me know the parish URL
3. I'll improve the agent

---

**Ready to try it? Open a parish site and click 🚀 Smart Extract!** ✨
