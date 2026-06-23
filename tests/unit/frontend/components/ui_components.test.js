import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import { Tooltip } from '../../../../scripts/ui_components';

test('displays tooltip content on hover (mocked)', () => {
  render(<Tooltip content="Test tooltip"><button>Hover Me</button></Tooltip>);
  expect(screen.getByText('Test tooltip')).toBeInTheDocument();
});
