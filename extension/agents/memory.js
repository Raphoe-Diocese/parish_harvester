/**
 * Memory System
 * 
 * Saves and retrieves learned patterns for bulletin extraction.
 * Allows the agent to get smarter over time and reduce AI costs.
 */

const STORAGE_KEY = 'agent_learned_patterns';

/**
 * Get learned pattern for a domain
 * @param {string} url - Current page URL
 * @param {Function} storageGet - Optional storage getter
 * @returns {Promise<Object|null>} Learned pattern or null
 */
async function getLearnedPattern(url, storageGet = null) {
  try {
    const domain = new URL(url).hostname;
    const patterns = await getAllPatterns(storageGet);
    
    if (patterns[domain]) {
      const pattern = patterns[domain];
      
      // Check if pattern is still valid (not too old)
      const ageInDays = (Date.now() - pattern.lastUsed) / (1000 * 60 * 60 * 24);
      if (ageInDays > 90) {
        console.log('📚 Pattern found but stale (', ageInDays.toFixed(0), 'days old)');
        return null;
      }
      
      console.log('📚 Found pattern:', {
        confidence: pattern.confidence,
        successRate: `${pattern.successCount}/${pattern.successCount + pattern.failCount}`,
        lastUsed: new Date(pattern.lastUsed).toLocaleDateString(),
      });
      
      return pattern;
    }
    
    console.log('📚 No pattern found for', domain);
    return null;
  } catch (error) {
    console.error('Failed to get learned pattern:', error);
    return null;
  }
}

/**
 * Save a successful extraction pattern
 * @param {string} url - Page URL
 * @param {Array} plan - The successful plan
 * @param {Object} result - Extraction result
 * @param {Function} storageSet - Optional storage setter
 */
async function savePattern(url, plan, result, storageSet = null) {
  try {
    const domain = new URL(url).hostname;
    const patterns = await getAllPatterns();
    
    const existing = patterns[domain];
    
    if (existing) {
      // Update existing pattern
      patterns[domain] = {
        ...existing,
        plan,
        successCount: (existing.successCount || 0) + 1,
        lastUsed: Date.now(),
        lastSuccess: Date.now(),
        confidence: calculateConfidence(existing.successCount + 1, existing.failCount || 0),
        urlPattern: detectUrlPattern(result.extracted?.url, existing.urlPattern),
      };
      
      console.log('💾 Updated pattern for', domain, '- confidence:', patterns[domain].confidence);
    } else {
      // Create new pattern
      patterns[domain] = {
        domain,
        plan,
        successCount: 1,
        failCount: 0,
        created: Date.now(),
        lastUsed: Date.now(),
        lastSuccess: Date.now(),
        confidence: 0.5, // Start at 50%
        urlPattern: detectUrlPattern(result.extracted?.url),
      };
      
      console.log('💾 Created new pattern for', domain);
    }
    
    await saveAllPatterns(patterns, storageSet);
  } catch (error) {
    console.error('Failed to save pattern:', error);
  }
}

/**
 * Record a pattern failure
 * @param {string} url - Page URL
 * @param {Function} storageSet - Optional storage setter
 */
async function recordFailure(url, storageSet = null) {
  try {
    const domain = new URL(url).hostname;
    const patterns = await getAllPatterns();
    
    if (patterns[domain]) {
      patterns[domain].failCount = (patterns[domain].failCount || 0) + 1;
      patterns[domain].confidence = calculateConfidence(
        patterns[domain].successCount || 0,
        patterns[domain].failCount
      );
      
      console.log('❌ Recorded failure for', domain, '- confidence:', patterns[domain].confidence);
      
      await saveAllPatterns(patterns, storageSet);
    }
  } catch (error) {
    console.error('Failed to record failure:', error);
  }
}

/**
 * Get all stored patterns
 */
async function getAllPatterns(storageGet = null) {
  const getStorage = storageGet || ((keys) => {
    return new Promise((resolve) => {
      chrome.storage.local.get(keys, resolve);
    });
  });

  const data = await getStorage([STORAGE_KEY]);
  return data[STORAGE_KEY] || {};
}

/**
 * Save all patterns
 */
async function saveAllPatterns(patterns, storageSet = null) {
  const setStorage = storageSet || ((items) => {
    return new Promise((resolve) => {
      chrome.storage.local.set(items, resolve);
    });
  });

  await setStorage({ [STORAGE_KEY]: patterns });
}

/**
 * Calculate confidence score based on success/fail ratio
 */
function calculateConfidence(successCount, failCount) {
  const total = successCount + failCount;
  if (total === 0) return 0.5;
  
  const ratio = successCount / total;
  
  // Apply some smoothing - need at least 3 successes for high confidence
  if (successCount < 3) {
    return Math.min(0.75, ratio);
  }
  
  return ratio;
}

/**
 * Detect URL pattern from successful extraction
 * Tries to identify date patterns in the URL
 */
function detectUrlPattern(url, existingPattern = null) {
  if (!url) return existingPattern;
  
  try {
    // Check for common date patterns
    const datePatterns = [
      { regex: /(\d{4})-(\d{2})-(\d{2})/, template: '{YYYY}-{MM}-{DD}' },
      { regex: /(\d{4})(\d{2})(\d{2})/, template: '{YYYY}{MM}{DD}' },
      { regex: /(\d{2})-(\d{2})-(\d{4})/, template: '{DD}-{MM}-{YYYY}' },
      { regex: /week[_-]?(\d+)/i, template: 'week-{W}' },
    ];
    
    for (const { regex, template } of datePatterns) {
      if (regex.test(url)) {
        const pattern = url.replace(regex, template);
        console.log('🔍 Detected URL pattern:', pattern);
        return pattern;
      }
    }
    
    return existingPattern;
  } catch (error) {
    return existingPattern;
  }
}

/**
 * Clear all learned patterns (for testing/reset)
 */
async function clearAllPatterns(storageSet = null) {
  console.log('🗑️ Clearing all learned patterns');
  await saveAllPatterns({}, storageSet);
}

/**
 * Get memory statistics
 */
async function getStats(storageGet = null) {
  const patterns = await getAllPatterns(storageGet);
  const domains = Object.keys(patterns);
  
  let totalSuccess = 0;
  let totalFail = 0;
  
  domains.forEach(domain => {
    totalSuccess += patterns[domain].successCount || 0;
    totalFail += patterns[domain].failCount || 0;
  });
  
  return {
    domainsLearned: domains.length,
    totalExtractions: totalSuccess + totalFail,
    successRate: totalSuccess / (totalSuccess + totalFail || 1),
    patterns,
  };
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    getLearnedPattern,
    savePattern,
    recordFailure,
    getAllPatterns,
    clearAllPatterns,
    getStats,
  };
}
