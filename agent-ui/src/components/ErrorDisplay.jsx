import React from 'react';
import { mapApiError } from '../../../scripts/error_handling';

const ErrorDisplay = ({ error }) => {
  if (!error) return null;
  const { title, message } = mapApiError(error);
  return (
    <div className="error-message">
      <h3>{title}</h3>
      <p>{message}</p>
    </div>
  );
};
export default ErrorDisplay;
