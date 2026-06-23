/**
 * Creates a scoped undo manager instance. Each instance maintains its own
 * history so independent features (e.g., profile edit, resource delete) don't
 * interfere with each other.
 *
 * Usage:
 *   const undoManager = createUndoManager();
 *   await undoManager.perform(
 *     (id, name) => saveProfile(id, name),      // action
 *     (result) => restoreProfile(result.prev),   // undo callback
 *     'user-1', 'Alice'                          // args to action
 *   );
 *   await undoManager.undo(); // calls restoreProfile
 */

export const createUndoManager = (maxHistory = 10) => {
  const history = [];

  /**
   * Execute an action and record it for undo.
   *
   * @param {Function} actionFn  — async or sync function to execute.
   * @param {Function} undoFn    — async or sync function called during undo.
   *                                Receives (result, ...args) where result is
   *                                whatever actionFn returned.
   * @param  {...any} args        — arguments forwarded to actionFn.
   * @returns {Promise<any>}      — the return value of actionFn.
   * @throws {TypeError}          — if undoFn is not provided.
   */
  const perform = async (actionFn, undoFn, ...args) => {
    if (typeof undoFn !== 'function') {
      throw new TypeError('undoFn is required — pass a callback that can revert this action');
    }
    if (typeof actionFn !== 'function') {
      throw new TypeError('actionFn must be a function');
    }

    let result;
    try {
      result = await actionFn(...args);
    } catch (err) {
      // Failed actions are NOT recorded in history.
      throw err;
    }

    // Record the entry only after the action succeeds.
    history.push({ undoFn, args, result });

    // Keep history bounded — drop the oldest entry when at capacity.
    if (history.length > maxHistory) {
      history.shift();
    }

    return result;
  };

  /**
   * Undo the most recent action.
   *
   * @returns {Promise<Object|null>} — the undone entry, or null if nothing to undo.
   * @throws {Error} — if the undo callback fails. On failure the entry is
   *                    re-pushed so the user can retry.
   */
  const undo = async () => {
    if (history.length === 0) return null;

    const entry = history.pop();
    try {
      await entry.undoFn(entry.result, ...entry.args);
      return entry;
    } catch (err) {
      // Re-push on failure so the action remains undoable.
      history.push(entry);
      throw err;
    }
  };

  /** Clear the undo history (e.g., after a successful save). */
  const clear = () => { history.length = 0; };

  /** Current number of undoable entries (read-only). */
  const length = () => history.length;

  return { perform, undo, clear, length };
};
