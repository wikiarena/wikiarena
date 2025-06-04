import math
from collections import defaultdict
from typing import Dict, List

class BradleyTerryModel:
    """Calculates Bradley-Terry ratings from pairwise game comparisons.

    This calculator expects individual pairwise outcomes to be added. 
    The logic for generating these pairs from a broader dataset of games 
    (e.g., all games for a specific task) should be handled externally.
    """
    
    def __init__(self):
        self.win_matrix = defaultdict(lambda: defaultdict(float))
        self.models = set() # Stores unique model keys

    def add_pairwise_comparison(self, 
                                model_a_key: str, 
                                model_b_key: str, 
                                model_a_steps: int, 
                                model_b_steps: int):
        """Adds a single pairwise comparison result between two models for a task.

        Args:
            model_a_key: Unique string identifier for model A.
            model_b_key: Unique string identifier for model B.
            model_a_steps: Number of steps model A took.
            model_b_steps: Number of steps model B took.
                         Fewer steps indicate a win.
        """
        if model_a_key == model_b_key:
            # Cannot compare a model against itself in a meaningful way for BT.
            return

        self.models.add(model_a_key)
        self.models.add(model_b_key)
        
        if model_a_steps < model_b_steps: # model_a wins
            self.win_matrix[model_a_key][model_b_key] += 1.0
        elif model_b_steps < model_a_steps: # model_b wins
            self.win_matrix[model_b_key][model_a_key] += 1.0
        else: # tie
            self.win_matrix[model_a_key][model_b_key] += 0.5
            self.win_matrix[model_b_key][model_a_key] += 0.5
    
    def calculate_strengths(self, iterations: int = 20) -> Dict[str, float]:
        """Calculate Bradley-Terry strengths using an iterative algorithm.

        The calculation is based on the formula:
            strength_i = W_i / sum(N_ij / (strength_i + strength_j) * strength_i for j!=i)
        where W_i is total wins for model i, N_ij is total games between i and j.
        """
        if not self.models:
            return {}

        strengths = {model: 1.0 for model in self.models}
        
        for _ in range(iterations):
            new_strengths = {}
            for model_i in self.models:
                # Total wins for model_i, including 0.5 for ties
                wins_i = sum(self.win_matrix[model_i].values())
                
                expected_denominator_sum = 0
                for model_j in self.models:
                    if model_i == model_j:
                        continue
                    
                    # Total games played between model_i and model_j
                    # N_ij = win_matrix[i][j] (i beat j) + win_matrix[j][i] (j beat i)
                    # This correctly accounts for ties if they are stored as 0.5 in both directions.
                    games_ij = self.win_matrix[model_i][model_j] + self.win_matrix[model_j][model_i]
                    
                    if games_ij > 0:
                        # Contribution to expected wins for model_i from games against model_j
                        # This is games_ij * (strength_i / (strength_i + strength_j))
                        # The formula for the denominator sum in BT is Sum_j!=i [ N_ij / (strength_i + strength_j) ]
                        # So, new_strength_i = wins_i / Sum_j!=i [ N_ij / (strength_i + strength_j) ]
                        # This part was: expected += games * (strengths[model] / (strengths[model] + strengths[opponent]))
                        # which is the sum of W_ij * P(i beats j).
                        # Let's re-check standard BT update.
                        # A common iterative update is:
                        # p_i = sum_j(wins_ij) / sum_j( (wins_ij + wins_ji) / (p_i + p_j) )
                        # where p_i is strength of model i. wins_ij is times i beat j.

                        expected_denominator_sum += games_ij / (strengths[model_i] + strengths[model_j])
                
                if expected_denominator_sum > 0:
                    new_strengths[model_i] = wins_i / expected_denominator_sum
                else:
                    # If a model has no games or only games against itself (filtered out),
                    # or if all opponents have zero strength and it also has zero strength
                    # leading to division by zero in expected_denominator_sum.
                    # Assign a base strength. If it has wins, it might be non-zero.
                    # If wins_i is also 0, it remains 1.0 (or could be lower if preferred).
                    new_strengths[model_i] = strengths[model_i] if wins_i == 0 else 1.0


            if not new_strengths: # Should not happen if self.models is not empty
                return strengths

            # Normalize strengths to have an average of 1.0 (or geometric mean of 1.0)
            # Using arithmetic mean for normalization:
            total_strength_sum = sum(new_strengths.values())
            num_models = len(new_strengths)
            if num_models > 0 and total_strength_sum > 0:
                avg_strength = total_strength_sum / num_models
                strengths = {m: s / avg_strength for m, s in new_strengths.items()}
            else: # All strengths might be zero if no games or wins
                strengths = new_strengths
        
        return strengths
    
    def strengths_to_elo(self, strengths: Dict[str, float], 
                         base_elo: int = 1200) -> Dict[str, int]:
        """Convert Bradley-Terry strengths to Elo ratings.
        A common formula is Elo = BaseElo + 400 * log10(strength).
        Assumes strengths are normalized around an average of 1.0.
        """
        elo_ratings = {}
        for model, strength in strengths.items():
            if strength > 0:
                # Ensure strength is positive to avoid math domain error with log10
                elo = base_elo + 400 * math.log10(strength)
                elo_ratings[model] = round(elo)
            else:
                # Assign a low Elo for zero or negative strength (e.g., if model never won and normalization results in 0)
                # Or, could assign base_elo if strength is 1.0 (neutral) before log.
                # A strength of exactly 0 might mean it never played or never won any fraction of a game.
                elo_ratings[model] = round(base_elo + 400 * math.log10(1e-9)) # Effectively very low Elo for 0 strength
        return elo_ratings

    def get_win_matrix_readable(self) -> Dict[str, Dict[str, float]]:
        """Returns a copy of the win matrix for inspection."""
        return {model: dict(opponents) for model, opponents in self.win_matrix.items()}

    def get_models(self) -> List[str]:
        """Returns a list of unique model keys that have participated."""
        return list(self.models)