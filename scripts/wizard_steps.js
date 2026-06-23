import React from 'react';

// Inside a wizard step component
export const WizardStepHelp = ({ message }) => (
  <div className="help-text">
    {message}
  </div>
);

// Example: <WizardStepHelp message="Please upload your primary document here. Supported formats: PDF, DOCX. Max file size: 10MB." />
