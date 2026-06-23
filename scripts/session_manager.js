let history = []; // Simple undo history
const MAX_HISTORY = 10;

export const performActionWithUndo = async (actionFn, ...args) => {
  const stateBefore = { /* capture relevant state */ };
  history.push({ action: actionFn, args, stateBefore });
  if (history.length > MAX_HISTORY) history.shift(); // Keep history bounded

  await actionFn(...args);
};

export const undoLastAction = () => {
  if (history.length === 0) return;
  const lastAction = history.pop();
  console.log('Undoing action:', lastAction.action.name);
};
