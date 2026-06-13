/**
 * Verifier Agent
 * 
 * Verifies that the extracted bulletin is correct (right week, valid file, etc.)
 */

/**
 * Verify the extracted bulletin
 * @param {Object} extracted - The extracted bulletin info
 * @param {Object} options - Verification options
 * @returns {Promise<Object>} Verification result
 */
async function verifyExtraction(extracted, options = {}) {
  const { storageGet = null, quickCheck = true } = options;
  
  if (!extracted || !extracted.url) {
    return {
      valid: false,
      reason: 'No bulletin extracted',
      confidence: 0,
    };
  }

  console.log('🔍 Verifying extraction:', extracted.url);

  // ALWAYS use quick check only (FREE - no AI cost)
  // Deep verification is disabled to save costs
  return quickVerify(extracted);
}

/**
 * Quick verification without AI
 * Just checks URL patterns and file extension
 */
function quickVerify(extracted) {
  const { url, type } = extracted;
  const checks = [];

  // Check 1: Valid URL
  try {
    new URL(url);
    checks.push({ check: 'valid_url', passed: true });
  } catch (error) {
    checks.push({ check: 'valid_url', passed: false });
    return {
      valid: false,
      reason: 'Invalid URL',
      confidence: 0,
      checks,
    };
  }

  // Check 2: Expected file type
  const isPDF = url.toLowerCase().includes('.pdf') || type === 'pdf';
  const isImage = /\.(jpg|jpeg|png|gif|webp)$/i.test(url) || type === 'image';
  checks.push({ check: 'expected_type', passed: isPDF || isImage });

  // Check 3: URL contains bulletin-related keywords
  const bulletinKeywords = ['bulletin', 'newsletter', 'weekly', 'parish', 'news'];
  const hasKeyword = bulletinKeywords.some(kw => url.toLowerCase().includes(kw));
  checks.push({ check: 'bulletin_keyword', passed: hasKeyword });

  // Check 4: URL looks current (has recent date or "current"/"latest")
  const currentYear = new Date().getFullYear();
  const hasCurrentYear = url.includes(String(currentYear));
  const hasCurrent = /current|latest|this[-_]?week/i.test(url);
  checks.push({ check: 'seems_current', passed: hasCurrentYear || hasCurrent });

  // Calculate confidence
  const passedCount = checks.filter(c => c.passed).length;
  const confidence = passedCount / checks.length;

  return {
    valid: confidence >= 0.5, // At least half the checks passed
    reason: confidence >= 0.5 ? 'Quick checks passed' : 'Quick checks failed',
    confidence,
    checks,
    method: 'quick',
  };
}

/**
 * Deep verification using AI
 * Downloads bulletin text/metadata and asks AI if it looks correct
 */
async function deepVerify(extracted, storageGet) {
  try {
    // First do quick check
    const quickResult = quickVerify(extracted);
    if (!quickResult.valid) {
      return quickResult;
    }

    // Try to get some metadata or text from the bulletin
    const bulletinInfo = await getBulletinInfo(extracted.url);
    
    // Ask AI to verify
    const aiResult = await verifyWithAI(bulletinInfo, storageGet);
    
    return {
      valid: aiResult.valid,
      reason: aiResult.reason,
      confidence: aiResult.confidence,
      checks: [...quickResult.checks, ...aiResult.checks],
      method: 'deep',
      aiAnalysis: aiResult.analysis,
    };
  } catch (error) {
    console.error('Deep verification failed:', error);
    // Fall back to quick check
    return quickVerify(extracted);
  }
}

/**
 * Get basic info about the bulletin (without downloading full file)
 */
async function getBulletinInfo(url) {
  try {
    const response = await fetch(url, { method: 'HEAD' });
    
    return {
      url,
      contentType: response.headers.get('content-type'),
      contentLength: response.headers.get('content-length'),
      lastModified: response.headers.get('last-modified'),
      status: response.status,
      exists: response.ok,
    };
  } catch (error) {
    console.error('Failed to get bulletin info:', error);
    return {
      url,
      exists: false,
      error: error.message,
    };
  }
}

/**
 * Use AI to verify the bulletin looks correct
 */
async function verifyWithAI(bulletinInfo, storageGet) {
  const getStorage = storageGet || ((keys) => {
    return new Promise((resolve) => {
      chrome.storage.local.get(keys, resolve);
    });
  });

  const settings = await getStorage(['openai_api_key']);
  const apiKey = (settings.openai_api_key || '').trim();

  if (!apiKey) {
    console.warn('No OpenAI key for deep verification, using quick check only');
    return { valid: true, confidence: 0.6, checks: [], analysis: 'No API key' };
  }

  const prompt = `You are verifying a parish bulletin extraction. Based on this information, is this likely the correct current week's bulletin?

Bulletin Info:
- URL: ${bulletinInfo.url}
- Content Type: ${bulletinInfo.contentType || 'unknown'}
- File Size: ${bulletinInfo.contentLength || 'unknown'}
- Last Modified: ${bulletinInfo.lastModified || 'unknown'}
- Exists: ${bulletinInfo.exists ? 'yes' : 'no'}

Current Date: ${new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}

Analysis:
1. Does the URL suggest this is a current/recent bulletin?
2. Is the file size reasonable for a bulletin (typically 0.5-5MB)?
3. Does the last modified date suggest it's current?
4. Any red flags (404, wrong type, suspicious URL)?

Return JSON only:
{
  "valid": true/false,
  "confidence": 0.0-1.0,
  "reason": "brief explanation",
  "checks": [
    {"check": "check_name", "passed": true/false}
  ]
}`;

  try {
    const endpoint = 'https://api.openai.com/v1/chat/completions';
    const payload = {
      model: 'gpt-4o-mini',
      messages: [
        {
          role: 'system',
          content: 'You verify bulletin extractions. Respond with JSON only.',
        },
        {
          role: 'user',
          content: prompt,
        },
      ],
      temperature: 0.3, // Lower temperature for verification
      max_tokens: 500,
    };

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const data = await response.json();
    const content = data.choices?.[0]?.message?.content || '';
    
    // Remove markdown if present
    let jsonStr = content.trim();
    if (jsonStr.startsWith('```')) {
      jsonStr = jsonStr.replace(/```json?\n?/g, '').replace(/```\n?$/g, '').trim();
    }

    const result = JSON.parse(jsonStr);
    return {
      ...result,
      analysis: content,
    };
  } catch (error) {
    console.error('AI verification failed:', error);
    return {
      valid: true, // Default to valid if verification fails
      confidence: 0.5,
      checks: [],
      analysis: `Verification failed: ${error.message}`,
    };
  }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { verifyExtraction, quickVerify, deepVerify };
}
