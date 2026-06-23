/**
 * Sanitize a string value to prevent XSS/leaks when surfacing to UI.
 * Only keeps safe characters — no HTML, no control chars.
 */
const sanitize = (value) => {
  if (typeof value !== 'string') return '';
  return value.replace(/[<>"'&]/g, (ch) => {
    const map = { '<': '', '>': '', '"': "'", "'": '', '&': '' };
    return map[ch] || '';
  }).trim().slice(0, 500); // cap length to prevent long-detail leaks
};

export const mapApiError = (error) => {
  // ------------------------------------------------------------------
  // 1. Network-level errors (axios sets error.request, no error.response)
  // ------------------------------------------------------------------
  if (error && !error.response) {
    if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
      return { title: 'Request Timed Out', message: 'The server took too long to respond. Please try again.' };
    }
    if (error.code === 'ERR_NETWORK' || error.message?.includes('Network Error')) {
      return { title: 'Connection Error', message: 'Could not connect to the server. Please check your internet connection and try again.' };
    }
    // Any other request-level failure (CORS blocked, DNS, etc.)
    return { title: 'Connection Error', message: 'A network error occurred. Please check your connection and try again.' };
  }

  // ------------------------------------------------------------------
  // 2. Server responded with an HTTP status — read the body error payload
  // ------------------------------------------------------------------
  const apiError = error.response?.data?.error || {};
  const code = apiError.code;

  switch (code) {
    case 'INVALID_INPUT':
      return {
        title: 'Invalid Input',
        message: `Please check your input: ${sanitize(apiError.details || '')}`,
      };

    case 'SESSION_EXPIRED':
      return {
        title: 'Session Expired',
        message: 'Your session has ended. Please log in again to continue.',
        requiresAuth: true,
      };

    case 'UNAUTHORIZED':
      return {
        title: 'Session Expired',
        message: 'Your session has ended. Please log in again to continue.',
        requiresAuth: true,
      };

    case 'FORBIDDEN':
      return {
        title: 'Access Denied',
        message: "You don't have permission to perform this action.",
      };

    case 'CONFLICT':
    case '409':
      return {
        title: 'Update Conflict',
        message: 'This data has been updated by someone else. Please refresh to see the latest version.',
      };

    case 'RATE_LIMITED':
      return {
        title: 'Slow Down',
        message: 'You\'re making too many requests. Please wait a moment and try again.',
      };

    case 'NOT_FOUND':
      return {
        title: 'Not Found',
        message: 'The requested resource no longer exists.',
      };

    case 'NETWORK_ERROR':
      // Server explicitly flagged a network-type error in its payload
      return {
        title: 'Connection Error',
        message: 'Could not connect to the server. Please check your internet connection and try again.',
      };

    default: {
      // Fall back to HTTP status code mapping when code is missing/unknown
      const status = error.response?.status;
      if (status === 401) {
        return { title: 'Session Expired', message: 'Your session has ended. Please log in again to continue.', requiresAuth: true };
      }
      if (status === 403) {
        return { title: 'Access Denied', message: "You don't have permission to perform this action." };
      }
      if (status === 404) {
        return { title: 'Not Found', message: 'The requested resource no longer exists.' };
      }
      return {
        title: 'An Unexpected Error Occurred',
        message: 'Please contact support if the problem persists.',
      };
    }
  }
};
