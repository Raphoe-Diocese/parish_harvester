/**
 * Executor Agent
 * 
 * Executes the plan created by the planner.
 * Actually performs actions: clicking, scrolling, extracting PDFs/images.
 */

/**
 * Execute an extraction plan
 * @param {Array} plan - Array of action objects
 * @param {Object} options - Execution options
 * @returns {Promise<Object>} Execution result
 */
async function executePlan(plan, options = {}) {
  const { maxRetries = 3, onProgress = null } = options;
  
  console.log('⚙️ Starting plan execution with', plan.length, 'steps');
  
  const results = [];
  let extracted = null;

  for (let i = 0; i < plan.length; i++) {
    const action = plan[i];
    console.log(`Step ${i + 1}/${plan.length}:`, action.type, action.description || '');
    
    if (onProgress) {
      onProgress({ step: i + 1, total: plan.length, action });
    }

    try {
      const result = await executeAction(action);
      results.push({ action, result, success: true });

      // If this was an extraction action, save the result
      if (action.type === 'extract_pdf' || action.type === 'extract_image') {
        extracted = result;
      }
    } catch (error) {
      console.error(`Step ${i + 1} failed:`, error.message);
      results.push({ action, error: error.message, success: false });
      
      // Decide whether to continue or abort
      if (action.critical !== false) {
        throw new Error(`Critical step failed: ${action.type} - ${error.message}`);
      }
    }
  }

  return {
    success: extracted !== null,
    extracted,
    results,
    stepsCompleted: results.filter(r => r.success).length,
    stepsTotal: plan.length,
  };
}

/**
 * Execute a single action
 */
async function executeAction(action) {
  switch (action.type) {
    case 'click':
      return await executeClick(action);
    
    case 'wait':
      return await executeWait(action);
    
    case 'extract_pdf':
      return await extractPDF(action);
    
    case 'extract_image':
      return await extractImage(action);
    
    case 'scroll':
      return await executeScroll(action);
    
    case 'navigate':
      return await executeNavigate(action);
    
    default:
      throw new Error(`Unknown action type: ${action.type}`);
  }
}

/**
 * Click an element
 */
async function executeClick(action) {
  const element = document.querySelector(action.selector);
  
  if (!element) {
    throw new Error(`Element not found: ${action.selector}`);
  }

  // Scroll into view first
  element.scrollIntoView({ behavior: 'smooth', block: 'center' });
  await sleep(300);

  // Click
  element.click();
  
  return { clicked: true, selector: action.selector };
}

/**
 * Wait for specified time
 */
async function executeWait(action) {
  const ms = action.ms || 1000;
  await sleep(ms);
  return { waited: ms };
}

/**
 * Extract a PDF
 */
async function extractPDF(action) {
  let url = action.url;
  
  // If no URL provided, try to get it from selector
  if (!url && action.selector) {
    const element = document.querySelector(action.selector);
    if (!element) {
      throw new Error(`PDF element not found: ${action.selector}`);
    }
    
    if (element.tagName === 'A') {
      url = element.href;
    } else if (element.tagName === 'IFRAME') {
      url = element.src;
    } else if (element.tagName === 'EMBED') {
      url = element.src;
    } else {
      throw new Error(`Cannot extract PDF from element type: ${element.tagName}`);
    }
  }

  if (!url) {
    throw new Error('No PDF URL found');
  }

  // Resolve relative URLs
  url = new URL(url, window.location.href).href;

  return {
    type: 'pdf',
    url,
    filename: extractFilenameFromUrl(url),
  };
}

/**
 * Extract an image
 */
async function extractImage(action) {
  const element = document.querySelector(action.selector);
  
  if (!element) {
    throw new Error(`Image element not found: ${action.selector}`);
  }

  let url;
  if (element.tagName === 'IMG') {
    url = element.src;
  } else if (element.tagName === 'A') {
    url = element.href;
  } else {
    // Try to find image inside element
    const img = element.querySelector('img');
    if (img) {
      url = img.src;
    } else {
      throw new Error('No image found in element');
    }
  }

  // Resolve relative URLs
  url = new URL(url, window.location.href).href;

  return {
    type: 'image',
    url,
    filename: extractFilenameFromUrl(url),
  };
}

/**
 * Scroll the page
 */
async function executeScroll(action) {
  const pixels = action.pixels || 500;
  const direction = action.direction || 'down';
  
  const scrollAmount = direction === 'down' ? pixels : -pixels;
  window.scrollBy({ top: scrollAmount, behavior: 'smooth' });
  
  await sleep(500); // Wait for scroll to complete
  
  return { scrolled: pixels, direction };
}

/**
 * Navigate to a URL
 */
async function executeNavigate(action) {
  window.location.href = action.url;
  
  // This will cause page reload, so execution will stop here
  return { navigated: action.url };
}

/**
 * Extract filename from URL
 */
function extractFilenameFromUrl(url) {
  try {
    const urlObj = new URL(url);
    const pathname = urlObj.pathname;
    const parts = pathname.split('/');
    return parts[parts.length - 1] || 'bulletin';
  } catch (error) {
    return 'bulletin';
  }
}

/**
 * Sleep helper
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { executePlan, executeAction };
}
