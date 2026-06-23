export const mapApiError = (error) => {
  const apiError = error.response?.data?.error || {};
  switch (apiError.code) {
    case 'INVALID_INPUT':
      return { title: 'Invalid Input', message: `Please check your input: ${apiError.details || ''}` };
    case 'SESSION_EXPIRED':
      return { title: 'Session Expired', message: 'Your session has ended. Please log in again to continue.', requiresAuth: true };
    case 'NETWORK_ERROR':
      return { title: 'Connection Error', message: 'Could not connect to the server. Please check your internet connection and try again.' };
    case '409': // Or 'CONFLICT'
      return { title: 'Update Conflict', message: 'This data has been updated by someone else. Please refresh to see the latest version.' };
    default:
      return { title: 'An Unexpected Error Occurred', message: 'Please contact support if the problem persists.' };
  }
};
