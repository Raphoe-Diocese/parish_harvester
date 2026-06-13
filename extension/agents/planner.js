/**
 * Planner Agent
 * 
 * Analyzes the current page and creates a step-by-step plan to extract the bulletin.
 * Uses GPT-4o-mini by default with optional Claude fallback for complex cases.
 */

/**
 * Create an extraction plan for the given page context
 * @param {Object} pageContext - Current page information
 * @param {Object} memory - Previously learned patterns (if any)
 * @param {Function} storageGet - Function to get from chrome.storage
 * @returns {Promise<Object>} Extraction plan
 */
async function createExtractionPlan(pageContext, memory = null, storageGet = null) {
  const config = typeof AGENT_CONFIG !== 'undefined' ? AGENT_CONFIG : {};
  
  // Check if we have a high-confidence learned pattern
  if (memory && memory.confidence >= (config.learning?.confidenceThreshold || 0.75)) {
    console.log('📚 Using learned pattern (confidence:', memory.confidence, ') - FREE!');
    return {
      source: 'learned_pattern',
      plan: memory.plan,
      confidence: memory.confidence,
      predictedUrl: memory.urlPattern ? generateUrlFromPattern(memory.urlPattern) : null,
    };
  }

  // Try simple pattern matching first (NO AI NEEDED - FREE!)
  console.log('🔍 Trying smart pattern matching (no AI cost)...');
  const simplePattern = trySimplePatternMatching(pageContext);
  if (simplePattern && simplePattern.confidence >= 0.7) {
    console.log('✅ Simple pattern worked! No AI needed - FREE');
    return {
      source: 'simple_pattern',
      plan: simplePattern.plan,
      confidence: simplePattern.confidence,
      predictedUrl: null,
      reasoning: 'Found using simple pattern matching',
    };
  }

  // No pattern - use FREE Mistral AI as last resort
  console.log('🤖 Using FREE Mistral AI fallback...');
  
  const prompt = buildPlanningPrompt(pageContext, memory);
  const response = await callPlanningAI(prompt, storageGet);
  
  if (!response || !response.plan) {
    throw new Error('Failed to create extraction plan');
  }

  return {
    source: 'mistral_free',
    plan: response.plan,
    confidence: 0.5, // New plans start at 50% confidence
    predictedUrl: response.nextWeekUrl || null,
    reasoning: response.reasoning || '',
  };
}

/**
 * Try to extract bulletin using simple pattern matching (NO AI - FREE!)
 * Looks for obvious patterns that don't need AI
 */
function trySimplePatternMatching(pageContext) {
  const { pdfLinks, iframes, url } = pageContext;
  
  // Strategy 1: Look for PDF links with "bulletin" keyword and current year
  const currentYear = new Date().getFullYear();
  const bulletinKeywords = ['bulletin', 'newsletter', 'weekly', 'current', 'latest', 'this week'];
  
  if (pdfLinks && pdfLinks.length > 0) {
    // Score each PDF link
    const scored = pdfLinks.map(link => {
      let score = 0;
      const linkText = (link.text || '').toLowerCase();
      const linkHref = (link.href || '').toLowerCase();
      const combined = linkText + ' ' + linkHref;
      
      // Has bulletin keyword?
      if (bulletinKeywords.some(kw => combined.includes(kw))) score += 3;
      
      // Has current year?
      if (combined.includes(String(currentYear))) score += 2;
      
      // Has "current" or "latest"?
      if (combined.includes('current') || combined.includes('latest')) score += 2;
      
      // Looks like a date pattern?
      if (/\d{4}[-_]\d{2}[-_]\d{2}/.test(combined)) score += 1;
      if (/\d{2}[-_]\d{2}[-_]\d{4}/.test(combined)) score += 1;
      
      // Short text (usually better than long descriptions)
      if (linkText.length > 0 && linkText.length < 30) score += 1;
      
      return { link, score };
    });
    
    // Sort by score
    scored.sort((a, b) => b.score - a.score);
    
    // If best score is high enough, use it!
    if (scored[0].score >= 5) {
      const bestLink = scored[0].link;
      console.log('Found high-confidence PDF link:', bestLink.href, 'score:', scored[0].score);
      
      return {
        confidence: Math.min(0.9, scored[0].score / 10),
        plan: [
          {
            type: 'extract_pdf',
            url: bestLink.href,
            selector: bestLink.selector,
            description: 'Extract bulletin PDF (found by pattern matching)',
          }
        ],
      };
    }
  }
  
  // Strategy 2: Single obvious PDF on page
  if (pdfLinks && pdfLinks.length === 1) {
    console.log('Found single PDF on page - likely the bulletin');
    return {
      confidence: 0.7,
      plan: [
        {
          type: 'extract_pdf',
          url: pdfLinks[0].href,
          selector: pdfLinks[0].selector,
          description: 'Extract only PDF on page',
        }
      ],
    };
  }
  
  // Strategy 3: Iframe with PDF (common for Google Drive embeds)
  if (iframes && iframes.length > 0) {
    const pdfIframe = iframes.find(iframe => 
      iframe.src && iframe.src.toLowerCase().includes('.pdf')
    );
    if (pdfIframe) {
      console.log('Found PDF in iframe');
      return {
        confidence: 0.75,
        plan: [
          {
            type: 'extract_pdf',
            url: pdfIframe.src,
            selector: pdfIframe.selector,
            description: 'Extract PDF from iframe',
          }
        ],
      };
    }
  }
  
  // No simple pattern found
  return null;
}

/**
 * Build the prompt for the planning AI
 */
function buildPlanningPrompt(pageContext, memory) {
  const { url, title, pdfLinks, iframes, images, links, domain } = pageContext;

  let prompt = `You are an autonomous web agent that extracts parish bulletins. Analyze this page and create a step-by-step plan.

CURRENT PAGE:
- URL: ${url}
- Title: ${title}
- Domain: ${domain}
- PDF Links: ${pdfLinks?.length || 0} found
- Iframes: ${iframes?.length || 0} found
- Images: ${images?.length || 0} found
- Total Links: ${links?.length || 0} found
`;

  // Add specific link information if available
  if (pdfLinks && pdfLinks.length > 0) {
    prompt += `\nPDF LINKS FOUND:\n`;
    pdfLinks.slice(0, 10).forEach((link, i) => {
      prompt += `${i + 1}. ${link.text || '(no text)'} → ${link.href}\n`;
    });
    if (pdfLinks.length > 10) {
      prompt += `... and ${pdfLinks.length - 10} more\n`;
    }
  }

  // Add memory/pattern information if available
  if (memory && memory.lastSuccess) {
    prompt += `\nHISTORICAL PATTERN (previous success):\n`;
    prompt += `- Last worked: ${memory.lastSuccess}\n`;
    prompt += `- Success rate: ${memory.successCount || 0}/${(memory.successCount || 0) + (memory.failCount || 0)}\n`;
    if (memory.plan) {
      prompt += `- Previous plan: ${JSON.stringify(memory.plan, null, 2)}\n`;
    }
  }

  prompt += `\nTASK:
Create a JSON plan to extract this week's parish bulletin. Your plan should be an array of action objects.

AVAILABLE ACTIONS:
1. click: {type: "click", selector: "CSS_SELECTOR", description: "what you're clicking"}
2. wait: {type: "wait", ms: 2000, reason: "why waiting"}
3. extract_pdf: {type: "extract_pdf", selector: "CSS_SELECTOR", url: "URL"}
4. extract_image: {type: "extract_image", selector: "CSS_SELECTOR"}
5. scroll: {type: "scroll", direction: "down", pixels: 500}
6. navigate: {type: "navigate", url: "URL"}

IMPORTANT RULES:
- Look for keywords: "bulletin", "newsletter", "weekly", "current", "this week", "latest"
- Prefer links with dates in current week
- If multiple bulletins, choose the MOST RECENT one
- Keep plan simple - usually 2-4 steps is enough
- Use reliable selectors (IDs preferred, then classes, then text content)
- Add wait steps after clicks (pages need time to load)

ALSO PREDICT:
Try to identify the URL pattern and predict next week's bulletin URL.
Common patterns:
- /bulletin-YYYY-MM-DD.pdf
- /bulletins/week-NN.pdf
- /newsletter-MMM-DD-YYYY.pdf

Return JSON ONLY (no markdown, no explanation):
{
  "plan": [
    {action objects here}
  ],
  "reasoning": "brief explanation of your approach",
  "nextWeekUrl": "predicted URL for next week or null",
  "confidence": 0.8
}`;

  return prompt;
}

/**
 * Call the AI to generate plan - uses FREE Mistral API
 */
async function callPlanningAI(prompt, storageGet) {
  const getStorage = storageGet || ((keys) => {
    return new Promise((resolve) => {
      chrome.storage.local.get(keys, resolve);
    });
  });

  const settings = await getStorage(['mistral_api_key']);
  const apiKey = (settings.mistral_api_key || '').trim();

  if (!apiKey) {
    throw new Error('Mistral API key not configured. Please add it in extension settings (FREE at console.mistral.ai)');
  }

  // Use FREE Mistral API
  const endpoint = 'https://api.mistral.ai/v1/chat/completions';
  const payload = {
    model: 'mistral-small-latest', // Free tier model
    messages: [
      {
        role: 'system',
        content: 'You are a web automation expert. Always respond with valid JSON only, no markdown formatting.',
      },
      {
        role: 'user',
        content: prompt,
      },
    ],
    temperature: 0.7,
    max_tokens: 2000,
  };

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Mistral API error:', response.status, errorText);
      throw new Error(`Mistral API error: ${response.status}`);
    }

    const data = await response.json();
    const content = data.choices?.[0]?.message?.content || '';
    
    // Remove markdown code blocks if present
    let jsonStr = content.trim();
    if (jsonStr.startsWith('```')) {
      jsonStr = jsonStr.replace(/```json?\n?/g, '').replace(/```\n?$/g, '').trim();
    }

    const result = JSON.parse(jsonStr);
    return result;
  } catch (error) {
    console.error('Failed to call planning AI:', error);
    throw error;
  }
}

/**
 * Generate next week's URL from a pattern
 */
function generateUrlFromPattern(pattern) {
  const now = new Date();
  const nextWeek = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
  
  // Replace date placeholders
  let url = pattern
    .replace('{YYYY}', nextWeek.getFullYear())
    .replace('{MM}', String(nextWeek.getMonth() + 1).padStart(2, '0'))
    .replace('{DD}', String(nextWeek.getDate()).padStart(2, '0'))
    .replace('{M}', nextWeek.getMonth() + 1)
    .replace('{D}', nextWeek.getDate());
  
  // Add more pattern support as needed
  
  return url;
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { createExtractionPlan, buildPlanningPrompt, callPlanningAI };
}
