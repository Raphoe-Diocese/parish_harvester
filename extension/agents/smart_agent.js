/**
 * Smart AI Agent
 * 
 * Main orchestrator that brings together planner, executor, verifier, and memory.
 * This is the autonomous agent that replaces the passive Gemini AI Help.
 */

/**
 * Extract bulletin from current page using autonomous agent
 * @param {Object} options - Extraction options
 * @returns {Promise<Object>} Extraction result
 */
async function smartExtractBulletin(options = {}) {
  const {
    url = window.location.href,
    storageGet = null,
    storageSet = null,
    onProgress = null,
    maxRetries = 3,
  } = options;

  console.log('🤖 Smart Agent starting extraction for:', url);
  
  if (onProgress) {
    onProgress({ stage: 'gathering_context', message: 'Analyzing page...' });
  }

  try {
    // Step 1: Gather page context
    const pageContext = await gatherPageContext();
    console.log('📄 Page context gathered:', {
      url: pageContext.url,
      pdfLinks: pageContext.pdfLinks?.length || 0,
      iframes: pageContext.iframes?.length || 0,
    });

    // Step 2: Check for learned pattern
    if (onProgress) {
      onProgress({ stage: 'checking_memory', message: 'Checking learned patterns...' });
    }
    
    const memory = await getLearnedPattern(url, storageGet);

    // Step 3: Create extraction plan
    if (onProgress) {
      onProgress({ stage: 'planning', message: memory ? 'Using learned pattern' : 'Creating plan with AI...' });
    }
    
    const planResult = await createExtractionPlan(pageContext, memory, storageGet);
    console.log('📋 Plan created:', planResult.source, '- confidence:', planResult.confidence);

    // Step 4: Execute the plan
    if (onProgress) {
      onProgress({ stage: 'executing', message: 'Executing extraction plan...' });
    }
    
    const executionResult = await executePlan(planResult.plan, {
      onProgress: (p) => {
        if (onProgress) {
          onProgress({
            stage: 'executing',
            message: `Step ${p.step}/${p.total}: ${p.action.description || p.action.type}`,
            progress: p.step / p.total,
          });
        }
      },
    });

    if (!executionResult.success || !executionResult.extracted) {
      throw new Error('Extraction failed - no bulletin found');
    }

    // Step 5: Verify the extracted bulletin
    if (onProgress) {
      onProgress({ stage: 'verifying', message: 'Verifying bulletin...' });
    }
    
    const verification = await verifyExtraction(executionResult.extracted, {
      storageGet,
      quickCheck: true, // Use quick check by default to save costs
    });

    console.log('✅ Verification result:', {
      valid: verification.valid,
      confidence: verification.confidence,
      reason: verification.reason,
    });

    // Step 6: Handle verification result
    if (!verification.valid && verification.confidence < 0.5) {
      // Verification failed badly - try correction
      if (onProgress) {
        onProgress({ stage: 'correcting', message: 'Verification failed, trying correction...' });
      }
      
      // TODO: Implement self-correction logic
      // For now, just record the failure
      await recordFailure(url, storageSet);
      
      return {
        success: false,
        error: 'Verification failed: ' + verification.reason,
        extracted: executionResult.extracted,
        verification,
        needsManualReview: true,
      };
    }

    // Step 7: Save successful pattern
    if (verification.valid && verification.confidence >= 0.7) {
      if (onProgress) {
        onProgress({ stage: 'learning', message: 'Saving pattern for future use...' });
      }
      
      await savePattern(url, planResult.plan, executionResult, storageSet);
    }

    // Success!
    if (onProgress) {
      onProgress({ stage: 'complete', message: 'Extraction complete!' });
    }

    return {
      success: true,
      extracted: executionResult.extracted,
      verification,
      planSource: planResult.source,
      confidence: verification.confidence,
      predictedNextWeekUrl: planResult.predictedUrl,
    };

  } catch (error) {
    console.error('❌ Smart extraction failed:', error);
    
    if (onProgress) {
      onProgress({ stage: 'error', message: error.message });
    }

    await recordFailure(url, storageSet).catch(() => {});

    return {
      success: false,
      error: error.message,
      needsManualReview: true,
    };
  }
}

/**
 * Gather information about the current page
 */
async function gatherPageContext() {
  const url = window.location.href;
  const title = document.title;
  const domain = window.location.hostname;

  // Find PDF links
  const pdfLinks = Array.from(document.querySelectorAll('a[href*=".pdf"], a[href*="pdf"]'))
    .map(a => ({
      text: a.textContent.trim(),
      href: a.href,
      selector: generateSelector(a),
    }))
    .slice(0, 20); // Limit to first 20

  // Find iframes
  const iframes = Array.from(document.querySelectorAll('iframe'))
    .map(iframe => ({
      src: iframe.src,
      selector: generateSelector(iframe),
    }))
    .slice(0, 10);

  // Find images (might be bulletin images)
  const images = Array.from(document.querySelectorAll('img[src*="bulletin"], img[src*="newsletter"], img[alt*="bulletin"], img[alt*="newsletter"]'))
    .map(img => ({
      src: img.src,
      alt: img.alt,
      selector: generateSelector(img),
    }))
    .slice(0, 10);

  // Find all links (for pattern analysis)
  const links = Array.from(document.querySelectorAll('a[href]'))
    .map(a => ({
      text: a.textContent.trim().substring(0, 50),
      href: a.href,
    }))
    .slice(0, 50);

  return {
    url,
    title,
    domain,
    pdfLinks,
    iframes,
    images,
    links,
  };
}

/**
 * Generate a CSS selector for an element
 */
function generateSelector(element) {
  // Prefer ID if available
  if (element.id) {
    return `#${element.id}`;
  }

  // Try to use class names
  if (element.className && typeof element.className === 'string') {
    const classes = element.className.trim().split(/\s+/).slice(0, 2);
    if (classes.length > 0 && classes[0]) {
      return element.tagName.toLowerCase() + '.' + classes.join('.');
    }
  }

  // Use href attribute for links
  if (element.tagName === 'A' && element.href) {
    const href = element.getAttribute('href');
    return `a[href="${href}"]`;
  }

  // Use src attribute for iframes/images
  if ((element.tagName === 'IFRAME' || element.tagName === 'IMG') && element.src) {
    const src = element.getAttribute('src');
    return `${element.tagName.toLowerCase()}[src="${src}"]`;
  }

  // Fallback to tag name with index
  const siblings = Array.from(element.parentElement?.children || [])
    .filter(e => e.tagName === element.tagName);
  const index = siblings.indexOf(element);
  
  return `${element.tagName.toLowerCase()}:nth-of-type(${index + 1})`;
}

/**
 * Get agent statistics
 */
async function getAgentStats(storageGet = null) {
  return await getStats(storageGet);
}

/**
 * Clear agent memory (for testing/reset)
 */
async function resetAgent(storageSet = null) {
  console.log('🔄 Resetting agent memory');
  await clearAllPatterns(storageSet);
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    smartExtractBulletin,
    gatherPageContext,
    getAgentStats,
    resetAgent,
  };
}
