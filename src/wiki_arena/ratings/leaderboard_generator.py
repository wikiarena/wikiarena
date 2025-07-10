from collections import defaultdict
from typing import Dict, List

from wiki_arena.storage import GameRepository
from wiki_arena.models import GameResult, Task
from .bradley_terry import BradleyTerryModel

class LeaderboardGenerator:
    """Orchestrates the generation of leaderboard ratings from game results."""

    def __init__(self, game_repository: GameRepository):
        """
        Initializes the LeaderboardGenerator.

        Args:
            game_repository: An instance of GameRepository to fetch game data.
        """
        self.game_repository = game_repository
        # Initialize bt_model here or in generate_elo_ratings for fresh run
        self.bt_model = BradleyTerryModel()

    def _fetch_and_group_games_by_task(self) -> Dict[str, List[GameResult]]:
        """Fetches all games and groups them by task ID."""
        all_games = self.game_repository.get_all_games()
        games_by_task: Dict[str, List[GameResult]] = defaultdict(list)

        for game in all_games:
            # Create a Task object from the game's config to get its canonical task_id
            task_obj = Task(
                start_page_title=game.config.start_page_title,
                target_page_title=game.config.target_page_title
            )
            task_id = task_obj.task_id # Uses get_sanitized_page_title internally
            games_by_task[task_id].append(game)
        
        return games_by_task

    def _populate_bradley_terry_comparisons(self, games_by_task: Dict[str, List[GameResult]]):
        """Populates the BradleyTerryModel with pairwise comparisons from grouped games."""
        for task_id, games_on_task in games_by_task.items():
            # Ensure there are at least two games to make a pair for comparison
            if len(games_on_task) < 2:
                continue

            for i in range(len(games_on_task)):
                for j in range(i + 1, len(games_on_task)):
                    game_a = games_on_task[i]
                    game_b = games_on_task[j]
                    
                    model_a_key = game_a.model.model_name
                    model_b_key = game_b.model.model_name
                    
                    # Avoid comparing a model against itself if the same model_key 
                    # appears multiple times for a task due to multiple runs being stored.
                    if model_a_key == model_b_key:
                        continue
                        
                    self.bt_model.add_pairwise_comparison(
                        model_a_key=model_a_key,
                        model_b_key=model_b_key,
                        model_a_steps=game_a.steps,
                        model_b_steps=game_b.steps
                    )

    def generate_elo_ratings(self, bt_iterations: int = 20, base_elo: int = 1200) -> Dict[str, int]:
        """
        Generates Elo ratings for all models based on the game results.
        This method re-initializes the BradleyTerryModel for a fresh calculation run.

        Args:
            bt_iterations: Number of iterations for the Bradley-Terry strength calculation.
            base_elo: The base Elo to use for converting strengths.

        Returns:
            A dictionary mapping model keys to their Elo ratings.
        """
        # Re-initialize for a fresh calculation run each time this method is called
        self.bt_model = BradleyTerryModel()
        
        games_by_task = self._fetch_and_group_games_by_task()
        self._populate_bradley_terry_comparisons(games_by_task)
        
        strengths = self.bt_model.calculate_strengths(iterations=bt_iterations)
        elo_ratings = self.bt_model.strengths_to_elo(strengths, base_elo=base_elo)
        
        return elo_ratings

    def get_current_win_matrix(self) -> Dict[str, Dict[str, float]]:
        """
        Returns the win matrix from the BradleyTerryModel instance.
        Note: This reflects the state after the last call to _populate_bradley_terry_comparisons.
        If generate_elo_ratings was just called, it will be the matrix used for that rating generation.
        """
        return self.bt_model.get_win_matrix_readable()

    def get_participating_models(self) -> List[str]:
        """
        Returns a list of unique model keys that have participated in comparisons.
        Note: This reflects the state after the last call to _populate_bradley_terry_comparisons.
        """
        return self.bt_model.get_models()