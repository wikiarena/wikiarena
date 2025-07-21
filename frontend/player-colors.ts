export const PLAYER_COLORS = {
  PLAYER1: '#3b82f6', // Blue-500 from Tailwind
  PLAYER2: '#f97316', // Orange-500 from Tailwind
};

/**
 * Returns the fixed color for a player based on their index.
 * Player 1 (index 0) is blue, Player 2 (index 1) is orange.
 * 
 * @param playerIndex The zero-based index of the player (0 or 1).
 * @returns The hex color code for the player.
 */
export function getPlayerColor(playerIndex: number): string {
  if (playerIndex < 0 || playerIndex > 1) {
    console.warn(`getPlayerColor called with invalid index: ${playerIndex}. Defaulting to Player 1 color.`);
    return PLAYER_COLORS.PLAYER1;
  }
  return playerIndex === 0 ? PLAYER_COLORS.PLAYER1 : PLAYER_COLORS.PLAYER2;
} 