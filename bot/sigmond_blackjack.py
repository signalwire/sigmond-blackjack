#!/usr/bin/env python3
"""
Dealer - The SignalWire Blackjack Dealer (Refactored)
An AI-powered blackjack dealer that plays casino-style blackjack via voice/video
Uses stateless architecture with centralized state management
"""

import json
import random
import argparse
import os
import mimetypes
from pathlib import Path
from signalwire_agents import AgentBase
from signalwire_agents.core.function_result import SwaigFunctionResult
from signalwire_agents.web.web_service import WebService
from fastapi import Request, Response

class BlackjackDealer(AgentBase):
    """Dealer - Your professional blackjack dealer"""
    
    def __init__(self):
        super().__init__(
            name="Dealer",
            route="/"  # Agent's internal route (will be mounted at /blackjack)
        )
        
        # Set up dealer personality
        self.prompt_add_section(
            "Personality", 
            "You are a professional blackjack dealer at a high-end casino. You're friendly but professional, "
            "explaining the rules clearly and maintaining the excitement of the game. You follow standard "
            "casino blackjack rules: dealer hits on 16 and below, stands on 17 and above."
        )
        
        # Define conversation contexts
        contexts = self.define_contexts()
        
        default_context = contexts.add_context("default") \
            .add_section("Goal", "Run an engaging blackjack game, manage bets, deal cards, and ensure fair play according to casino rules.")
        
        # Betting phase - this is the starting point
        default_context.add_step("betting") \
            .add_section("Current Task", "Take the player's bet") \
            .add_bullets("Betting Process", [
                "The player has ${global_data.current_chips} chips",
                "Ask how much they'd like to bet (minimum 10, maximum ${global_data.current_chips})",
                "When they tell you an amount, call place_bet function with that amount",
            ]) \
            .set_step_criteria("A valid bet has been placed and cards have been dealt") \
            .set_functions(["place_bet"]) \
            .set_valid_steps(["playing"])
        
        # Playing phase
        default_context.add_step("playing") \
            .add_section("Current Task", "Manage the active blackjack hand") \
            .add_bullets("CRITICAL RULES - YOU MUST FOLLOW THESE", [
                "The player currently has ${global_data.game_state.player_score} points",
                "When player says 'hit' or wants another card: YOU MUST CALL THE hit FUNCTION",
                "When player says 'stand' or wants to stay: YOU MUST CALL THE stand FUNCTION", 
                "When player says 'double down': YOU MUST CALL THE double_down FUNCTION",
                "Split is NOT available at this table - do not offer it as an option",
                "NEVER make up cards or scores - ONLY use what the functions return",
                "NEVER deal cards yourself - the hit function deals cards",
                "NEVER calculate scores yourself - the functions calculate scores",
                "The hit function will tell you EXACTLY what card was drawn and the new score",
                "If the function says 'the hand continues', keep playing - player has NOT busted",
                "Only say the player busted if the function explicitly says 'bust'"
            ]) \
            .set_step_criteria("Hand is complete and the winner is determined.") \
            .set_functions(["hit", "stand", "double_down"]) \
            .set_valid_steps(["hand_complete", "game_over"])


        # Post-Game phase
        default_context.add_step("hand_complete") \
            .add_section("Current Task", "The hand is complete. Review the results and wait for player's decision.") \
            .add_bullets("Important Instructions", [
                "The cards are still on the table - explain what happened in this hand",
                "Tell the user their chip count and how much they won or lost",
                "Ask if they want to play another hand",
                "DO NOT take any bets or start a new game until you call new_hand",
                "If the user wants to play again, you MUST call new_hand first",
                "The new_hand function will reset the table and change to betting step",
                "Only after calling new_hand can you take a new bet"
            ]) \
            .set_step_criteria("User has indicated whether they want to play another hand") \
            .set_functions(["new_hand"]) \
            .set_valid_steps(["betting"])
        
        # Game Over phase - when player runs out of chips
        default_context.add_step("game_over") \
            .add_section("Current Task", "The game is over. The player has run out of chips.") \
            .add_bullets("Important Instructions", [
                "The cards are still on the table - explain what happened in this final hand",
                "Tell the user they have no chips left and the game is over",
                "Thank them for playing",
                "Ask if they want to hang up or stay connected",
                "You cannot start a new game - they are out of chips",
                "Be sympathetic but professional about their loss"
            ]) \
            .set_step_criteria("User has acknowledged the game is over") \
            .set_functions([]) \
            .set_valid_steps([])
        
        # No resolution phase needed - handled automatically in hit/stand/double_down
        
        # Helper function to get/initialize game state
        def get_game_state(raw_data):
            """Get the current game state from global_data, or initialize if needed"""
            global_data = raw_data.get('global_data', {})
            
            # Default state structure
            default = {
                "deck": [],
                "player_hand": [],
                "dealer_hand": [],
                "player_score": 0,
                "dealer_score": 0,
                "current_bet": 0,
                "player_chips": 1000,
                "game_phase": "waiting",  # waiting, bet_placed, playing, resolution
                "hand_in_progress": False
            }
            
            return global_data.get('game_state', default), global_data
        
        # Helper function to add save action to result
        def add_save_action(result, game_state, global_data):
            """Add the save game state action to the result"""
            global_data['game_state'] = game_state
            # Also update top-level chip count for AI visibility
            global_data['current_chips'] = game_state['player_chips']
            result.update_global_data(global_data)
            return result
        
        # Helper function to resolve the hand and determine payouts
        def resolve_hand_internally(game_state):
            """Resolve the hand and update chips - returns result text"""
            player_score = game_state["player_score"]
            dealer_score = game_state["dealer_score"]
            bet = game_state["current_bet"]
            
            # Determine winner
            if player_score > 21:
                result_text = "You bust. House wins."
                winnings = 0
            elif dealer_score > 21:
                result_text = "I bust! You win!"
                winnings = bet * 2
            elif player_score > dealer_score:
                result_text = "You win!"
                winnings = bet * 2
            elif dealer_score > player_score:
                result_text = "House wins."
                winnings = 0
            else:
                result_text = "Push. We tied."
                winnings = bet  # Return the bet
            
            # Check for blackjack bonus
            if player_score == 21 and len(game_state["player_hand"]) == 2 and dealer_score != 21:
                result_text = "Blackjack pays three to two!"
                winnings = int(bet * 2.5)
            
            game_state["player_chips"] += winnings
            game_state["hand_in_progress"] = False
            game_state["game_phase"] = "waiting"
            
            # Don't clear hands here - keep them for display in hand_complete step
            response = f"\n\nHand complete! {result_text}\n"
            response += f"Player had {player_score}, Dealer had {dealer_score}.\n"
            if winnings > bet:
                response += f"Player wins {winnings - bet} chips! "
            elif winnings == bet:
                response += f"Player's bet of {bet} chips is returned. "
            else:
                response += f"Player loses their {bet} chip bet. "
            response += f"Player now has {game_state['player_chips']} chips total."
            
            if game_state["player_chips"] < 10:
                response += "\n\nYou're out of chips! Game over. Thanks for playing!"
            
            return response, result_text, winnings
        
        # Define game functions
        @self.tool(
            name="place_bet",
            description="Place a bet to start a new hand",
            parameters={
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "integer",
                        "description": "The amount of chips to bet",
                        "minimum": 10
                    }
                },
                "required": ["amount"]
            }
        )
        def place_bet(args, raw_data):
            """Place a bet and prepare for a new hand"""
            game_state, global_data = get_game_state(raw_data)
            amount = args["amount"]
            
            # Check if a hand is already in progress
            if game_state.get("hand_in_progress", False):
                return SwaigFunctionResult("There's already a hand in progress. Please finish it first.")
            
            # Check if player is out of chips
            if game_state["player_chips"] < 10:
                return SwaigFunctionResult(f"You only have {game_state['player_chips']} chips left, which is below the minimum bet of 10. Game over! Thanks for playing!")
            
            if amount > game_state["player_chips"]:
                return SwaigFunctionResult(f"You don't have that many chips. You have {game_state['player_chips']} chips.")
            
            if amount < 10:
                return SwaigFunctionResult("Minimum bet is ten chips at this table.")
            
            # Update state for new bet
            game_state["current_bet"] = amount
            game_state["player_chips"] -= amount
            game_state["game_phase"] = "bet_placed"  # Ready to deal cards
            game_state["hand_in_progress"] = True
            
            # Clear hands for new game
            game_state["player_hand"] = []
            game_state["dealer_hand"] = []
            game_state["player_score"] = 0
            game_state["dealer_score"] = 0
            
            # Save state first
            global_data['game_state'] = game_state
            
            # Now automatically deal the cards
            # Check if we have enough cards (need at least 15 for safety)
            if len(game_state["deck"]) < 15:
                game_state["deck"] = self._create_deck()
                random.shuffle(game_state["deck"])
                shuffled_new_deck = True
            else:
                shuffled_new_deck = False
            
            # Deal cards
            game_state["player_hand"] = [
                game_state["deck"].pop(),
                game_state["deck"].pop()
            ]
            game_state["dealer_hand"] = [
                game_state["deck"].pop(),
                game_state["deck"].pop()
            ]
            
            # Calculate scores
            game_state["player_score"] = self._calculate_score(game_state["player_hand"])
            game_state["dealer_score"] = self._calculate_score(game_state["dealer_hand"])
            game_state["game_phase"] = "playing"
            
            # Build response
            response = f"Perfect! You've bet {amount} chips. You have {game_state['player_chips']} chips remaining.\n\n"
            if shuffled_new_deck:
                response += "Shuffling a fresh deck.\n\n"
            
            player_cards_str = ", ".join([self._card_name(card) for card in game_state["player_hand"]])
            dealer_visible = self._card_name(game_state["dealer_hand"][0])
            
            response += f"Cards dealt! You have: {player_cards_str} for a total of {game_state['player_score']} points.\n"
            response += f"I'm showing {dealer_visible} with my other card face down."
            
            # Check for blackjack
            if game_state["player_score"] == 21:
                response += "\n\nBlackjack! Twenty-one!"
                # Play dealer's hand and resolve immediately
                response += self._play_dealer_hand(game_state)
                resolution_text, result_text, winnings = resolve_hand_internally(game_state)
                response += resolution_text
            else:
                response += "\n\nThe hand is now in play. What would you like to do?"
            
            result = SwaigFunctionResult(response)
            
            # Save complete state
            add_save_action(result, game_state, global_data)
            
            # Send UI updates
            # Send a clear event to ensure UI is clean before dealing
            result.swml_user_event({
                "type": "clear_table",
                "chips": game_state["player_chips"] + amount
            })
            
            result.swml_user_event({
                "type": "bet_placed",
                "amount": amount,
                "remaining_chips": game_state["player_chips"]
            })
            
            result.swml_user_event({
                "type": "cards_dealt",
                "player_hand": game_state["player_hand"],
                "dealer_hand": [game_state["dealer_hand"][0], None],  # Hide hole card
                "player_score": game_state["player_score"],
                "dealer_visible_score": self._calculate_score([game_state["dealer_hand"][0]])
            })
            
            # If blackjack, send resolution events and change to appropriate step
            if game_state["player_score"] == 21:
                result.swml_user_event({
                    "type": "dealer_play",
                    "dealer_hand": game_state["dealer_hand"],
                    "dealer_score": game_state["dealer_score"],
                    "dealer_busted": game_state["dealer_score"] > 21
                })
                
                result.swml_user_event({
                    "type": "hand_resolved",
                    "result": result_text,
                    "player_score": game_state["player_score"],
                    "dealer_score": game_state["dealer_score"],
                    "winnings": winnings,
                    "total_chips": game_state["player_chips"]
                })
                
                # Change to game_over if out of chips, otherwise hand_complete
                if game_state["player_chips"] < 10:
                    result.swml_change_step("game_over")
                else:
                    result.swml_change_step("hand_complete")
            
            return result
        
        @self.tool(
            name="hit",
            description="Player takes another card",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
        def hit(args, raw_data):
            """Deal another card to the player"""
            game_state, global_data = get_game_state(raw_data)
            
            # Verify we can hit
            if game_state["game_phase"] != "playing":
                return SwaigFunctionResult("You can't hit right now. The hand is not in play.")
            
            if not game_state.get("hand_in_progress", False):
                return SwaigFunctionResult("No hand in progress. Please place a bet first.")
            
            # Draw a card
            new_card = game_state["deck"].pop()
            game_state["player_hand"].append(new_card)
            game_state["player_score"] = self._calculate_score(game_state["player_hand"])
            
            # Build response
            player_cards_str = ", ".join([self._card_name(card) for card in game_state["player_hand"]])
            response = f"The player hits and receives: {self._card_name(new_card)}.\n"
            response += f"Player's complete hand: {player_cards_str}.\n"
            response += f"Player's total: {game_state['player_score']} points."
            
            if game_state["player_score"] > 21:
                response += " That's a bust! You're over twenty-one."
                # Resolve the hand immediately
                resolution_text, result_text, winnings = resolve_hand_internally(game_state)
                response += resolution_text
            elif game_state["player_score"] == 21:
                response += " Twenty-one! Perfect!"
                # Auto-play dealer's hand
                response += self._play_dealer_hand(game_state)
                # Resolve the hand
                resolution_text, result_text, winnings = resolve_hand_internally(game_state)
                response += resolution_text
            else:
                # Clearly state the situation and current score
                response += f"\n\nYou have {game_state['player_score']} points. The hand continues. What would you like to do?"
                result_text = None
                winnings = None
            
            result = SwaigFunctionResult(response)
            
            # Save state
            add_save_action(result, game_state, global_data)
            
            # Send UI update
            result.swml_user_event({
                "type": "player_hit",
                "new_card": new_card,
                "player_hand": game_state["player_hand"],
                "player_score": game_state["player_score"],
                "busted": game_state["player_score"] > 21
            })
            
            # If hand is resolved, send updates
            if game_state["player_score"] >= 21:
                if game_state["player_score"] == 21:
                    result.swml_user_event({
                        "type": "dealer_play",
                        "dealer_hand": game_state["dealer_hand"],
                        "dealer_score": game_state["dealer_score"],
                        "dealer_busted": game_state["dealer_score"] > 21
                    })
                if result_text and winnings is not None:
                    result.swml_user_event({
                        "type": "hand_resolved",
                        "result": result_text,
                        "player_score": game_state["player_score"],
                        "dealer_score": game_state["dealer_score"],
                        "winnings": winnings,
                        "total_chips": game_state["player_chips"]
                    })
                    # Change to game_over if out of chips, otherwise hand_complete
                    if game_state["player_chips"] < 10:
                        result.swml_change_step("game_over")
                    else:
                        result.swml_change_step("hand_complete")
            
            return result
        
        @self.tool(
            name="stand",
            description="Player stands with current hand",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
        def stand(args, raw_data):
            """Player stands, dealer's turn begins"""
            game_state, global_data = get_game_state(raw_data)
            
            # Verify we can stand
            if game_state["game_phase"] != "playing":
                return SwaigFunctionResult("You can't stand right now. The hand is not in play.")
            
            if not game_state.get("hand_in_progress", False):
                return SwaigFunctionResult("No hand in progress. Please place a bet first.")
            
            response = f"The player stands with {game_state['player_score']} points. Now it's the dealer's turn.\n"
            
            # Play dealer's hand
            response += self._play_dealer_hand(game_state)
            
            # Resolve the hand immediately
            resolution_text, result_text, winnings = resolve_hand_internally(game_state)
            response += resolution_text
            
            result = SwaigFunctionResult(response)
            
            # Save state
            add_save_action(result, game_state, global_data)
            
            # Send UI updates
            result.swml_user_event({
                "type": "player_stand",
                "player_score": game_state["player_score"]
            })
            
            result.swml_user_event({
                "type": "dealer_play",
                "dealer_hand": game_state["dealer_hand"],
                "dealer_score": game_state["dealer_score"],
                "dealer_busted": game_state["dealer_score"] > 21
            })
            
            result.swml_user_event({
                "type": "hand_resolved",
                "result": result_text,
                "player_score": game_state["player_score"],
                "dealer_score": game_state["dealer_score"],
                "winnings": winnings,
                "total_chips": game_state["player_chips"]
            })
            
            # Change to game_over if out of chips, otherwise hand_complete
            if game_state["player_chips"] < 10:
                result.swml_change_step("game_over")
            else:
                result.swml_change_step("hand_complete")
            
            return result
        
        @self.tool(
            name="double_down",
            description="Double the bet and take exactly one more card",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
        def double_down(args, raw_data):
            """Double down - double bet, take one card, then stand"""
            game_state, global_data = get_game_state(raw_data)
            
            # Verify we can double down
            if game_state["game_phase"] != "playing":
                return SwaigFunctionResult("You can't double down right now.")
            
            if len(game_state["player_hand"]) != 2:
                return SwaigFunctionResult("You can only double down on your first two cards.")
            
            if game_state["current_bet"] > game_state["player_chips"]:
                return SwaigFunctionResult(f"You need {game_state['current_bet']} more chips to double down.")
            
            # Double the bet
            game_state["player_chips"] -= game_state["current_bet"]
            game_state["current_bet"] *= 2
            
            # Take one card
            new_card = game_state["deck"].pop()
            game_state["player_hand"].append(new_card)
            game_state["player_score"] = self._calculate_score(game_state["player_hand"])
            
            response = f"The player doubles down! The bet is now doubled to {game_state['current_bet']} chips.\n"
            response += f"Player receives one final card: {self._card_name(new_card)}.\n"
            response += f"Player's final total: {game_state['player_score']} points. Player has {game_state['player_chips']} chips remaining."
            
            if game_state["player_score"] > 21:
                response += " That's a bust!"
                # Resolve immediately
                resolution_text, result_text, winnings = resolve_hand_internally(game_state)
                response += resolution_text
            else:
                # Dealer plays
                response += "\n\n" + self._play_dealer_hand(game_state)
                # Resolve the hand
                resolution_text, result_text, winnings = resolve_hand_internally(game_state)
                response += resolution_text
            
            result = SwaigFunctionResult(response)
            
            # Save state
            add_save_action(result, game_state, global_data)
            
            # Send UI updates
            result.swml_user_event({
                "type": "double_down",
                "new_bet": game_state["current_bet"],
                "new_card": new_card,
                "player_hand": game_state["player_hand"],
                "player_score": game_state["player_score"],
                "remaining_chips": game_state["player_chips"]
            })
            
            if game_state["player_score"] <= 21:
                result.swml_user_event({
                    "type": "dealer_play",
                    "dealer_hand": game_state["dealer_hand"],
                    "dealer_score": game_state["dealer_score"],
                    "dealer_busted": game_state["dealer_score"] > 21
                })
            
            result.swml_user_event({
                "type": "hand_resolved",
                "result": result_text,
                "player_score": game_state["player_score"],
                "dealer_score": game_state["dealer_score"],
                "winnings": winnings,
                "total_chips": game_state["player_chips"]
            })
            
            # Change to game_over if out of chips, otherwise hand_complete
            if game_state["player_chips"] < 10:
                result.swml_change_step("game_over")
            else:
                result.swml_change_step("hand_complete")
            
            return result
        
        @self.tool(
            name="new_hand",
            description="Start a new hand after the current one is complete",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
        def new_hand(args, raw_data):
            """Start a new hand and transition back to betting step"""
            game_state, global_data = get_game_state(raw_data)
            
            # Reset the game state for a new hand
            game_state["player_hand"] = []
            game_state["dealer_hand"] = []
            game_state["player_score"] = 0
            game_state["dealer_score"] = 0
            game_state["current_bet"] = 0
            game_state["hand_in_progress"] = False
            game_state["game_phase"] = "waiting"
            
            # Create response that changes step and resets UI
            result = SwaigFunctionResult(f"Starting a new hand. You have {game_state['player_chips']} chips.")
            
            # Save the reset state
            add_save_action(result, game_state, global_data)
            
            # Change to betting step
            result.swml_change_step("betting")
            
            # Send UI reset event to clear the table
            result.swml_user_event({
                "type": "game_reset",
                "chips": game_state["player_chips"]
            })
            
            return result
        
        # No need for resolve_hand or reset_game - all handled automatically
        # Configure voice
        self.add_language(
            name="English",
            code="en-US",
            voice="elevenlabs.adam"
        )
        
        # Add game-related hints for speech recognition
        self.add_hints([
            "blackjack",
            "twenty one",
            "hit",
            "stand",
            "double down",
            "bet",
            "all in",
            "dealer",
            "cards"
        ])
        
        # Set conversation parameters
        # Get the web root from environment variable or use local server
        web_root = os.environ.get("BLACKJACK_WEB_ROOT")
        if not web_root:
            # Default to local server when not specified
            port = int(os.environ.get("PORT", 5000))
            web_root = f"http://localhost:{port}"
            print(f"BLACKJACK_WEB_ROOT not set, using local server: {web_root}")
        
        self.set_params({
            "video_talking_file": f"{web_root}/sigmond_bj_talking.mp4",
            "video_idle_file": f"{web_root}/sigmond_bj_idle.mp4",
            "vad_config": "75",
            "end_of_speech_timeout": 300,
            "background_file": f"{web_root}/casino.mp3"
        })


        
        # Optional post-prompt URL from environment
        post_prompt_url = os.environ.get("BLACKJACK_POST_PROMPT_URL")
        if post_prompt_url:
            self.set_post_prompt("Summarize the conversation, including all the details about the tarot reading.") 
            self.set_post_prompt_url(post_prompt_url)
        
        # Initialize global data
        self.set_global_data({
            "assistant_name": "Dealer",
            "game": "Blackjack",
            "rules": "Dealer hits on 16, stands on 17",
            "starting_chips": 1000,
            "current_chips": 1000  # Start with initial chip count visible
        })
    
    def _build_webhook_url(self, endpoint: str, query_params: dict = None) -> str:
        """Override to ensure SWAIG URLs include /blackjack prefix"""
        # Get the base URL from parent
        url = super()._build_webhook_url(endpoint, query_params)
        
        # If the URL doesn't include /blackjack, add it before the endpoint
        if '/blackjack' not in url:
            # Parse the URL to modify the path
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(url)
            
            # Find where /swaig starts in the path and insert /blackjack before it
            if '/swaig' in parsed.path:
                new_path = parsed.path.replace('/swaig', '/blackjack/swaig')
            elif '/post_prompt' in parsed.path:
                new_path = parsed.path.replace('/post_prompt', '/blackjack/post_prompt')
            else:
                # Generic case - add /blackjack at the beginning of the path
                new_path = '/blackjack' + parsed.path
            
            # Reconstruct the URL with the modified path
            url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                new_path,
                parsed.params,
                parsed.query,
                parsed.fragment
            ))
        
        return url
    
    def _play_dealer_hand(self, game_state):
        """Play out the dealer's hand according to casino rules"""
        dealer_cards_str = ", ".join([self._card_name(card) for card in game_state["dealer_hand"]])
        response = f"\nDealer reveals hole card. Dealer's complete hand: {dealer_cards_str} for {game_state['dealer_score']} points.\n"
        
        # Dealer draws cards according to rules
        while game_state["dealer_score"] < 17:
            new_card = game_state["deck"].pop()
            game_state["dealer_hand"].append(new_card)
            game_state["dealer_score"] = self._calculate_score(game_state["dealer_hand"])
            response += f"Dealer draws {self._card_name(new_card)}. Dealer now has {game_state['dealer_score']} points.\n"
        
        if game_state["dealer_score"] > 21:
            response += "Dealer busts! Over 21!"
        else:
            response += f"Dealer stands with {game_state['dealer_score']} points."
        
        return response
    
    def _create_deck(self):
        """Create a standard 52-card deck"""
        suits = ['hearts', 'diamonds', 'clubs', 'spades']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'jack', 'queen', 'king', 'ace']
        deck = []
        for suit in suits:
            for rank in ranks:
                value = 10 if rank in ['jack', 'queen', 'king'] else 11 if rank == 'ace' else int(rank)
                deck.append({
                    'rank': rank,
                    'suit': suit,
                    'value': value,
                    'image': f"{rank}_of_{suit}.png"
                })
        return deck
    
    def _calculate_score(self, hand):
        """Calculate the score of a hand, handling aces appropriately"""
        score = sum(card['value'] for card in hand)
        aces = sum(1 for card in hand if card['rank'] == 'ace')
        
        # Adjust for aces
        while score > 21 and aces > 0:
            score -= 10
            aces -= 1
        
        return score
    
    def _card_name(self, card):
        """Get the display name of a card"""
        return f"{card['rank'].capitalize()} of {card['suit'].capitalize()}"
    
    def _get_content_type(self, file_path: str) -> str:
        """Get the content type for a file based on its extension"""
        content_type, _ = mimetypes.guess_type(file_path)
        if content_type:
            return content_type
        # Default types for common web files
        ext = Path(file_path).suffix.lower()
        return {
            '.html': 'text/html',
            '.js': 'application/javascript',
            '.css': 'text/css',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.mp4': 'video/mp4',
            '.mp3': 'audio/mpeg',
            '.json': 'application/json',
        }.get(ext, 'application/octet-stream')
    
    def _serve_static_file(self, file_path: Path) -> Response:
        """Serve a static file from the web directory"""
        if not file_path.exists():
            return Response(
                content="File not found",
                status_code=404,
                media_type="text/plain"
            )
        
        try:
            # Read file content
            if file_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.mp4', '.mp3']:
                # Binary files
                with open(file_path, 'rb') as f:
                    content = f.read()
            else:
                # Text files
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            # Get content type
            content_type = self._get_content_type(str(file_path))
            
            return Response(
                content=content,
                media_type=content_type
            )
        except Exception as e:
            return Response(
                content=f"Error reading file: {str(e)}",
                status_code=500,
                media_type="text/plain"
            )
    
    def _register_routes(self, router):
        """Override to add custom routes for static files and SWML"""
        # First register parent routes (this includes SWML at root)
        super()._register_routes(router)
    
    async def _handle_root_request(self, request: Request):
        """Override to serve appropriate content based on path and method"""
        path = request.url.path.rstrip('/')
        
        # For root path
        if path == '' or path == '/':
            # POST requests to root should return SWML (for SignalWire calls)
            if request.method == 'POST':
                return await super()._handle_root_request(request)
            # GET requests to root return the web interface
            else:
                bot_dir = Path(__file__).parent
                web_root = bot_dir.parent / 'web'
                index_file = web_root / 'client' / 'index.html'
                return self._serve_static_file(index_file)
        
        # For all other paths, use parent implementation
        return await super()._handle_root_request(request)
    
    def serve(self, host=None, port=None):
        """Override serve to properly set up custom routing"""
        import uvicorn
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        
        if self._app is None:
            # Create a new FastAPI app
            app = FastAPI(redirect_slashes=False)
            
            # Add CORS middleware
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
            
            # Add health check endpoints
            @app.get("/health")
            @app.post("/health")
            async def health_check():
                return {
                    "status": "healthy",
                    "agent": self.get_name(),
                    "route": self.route
                }
            
            # Register our custom catch-all FIRST (before parent routes)
            @app.get("/{full_path:path}")
            @app.post("/{full_path:path}")
            async def handle_all_custom_routes(request: Request, full_path: str):
                """Custom route handler for everything"""
                
                # Check authentication first
                if not self._check_basic_auth(request):
                    return Response(
                        content='{"error": "Unauthorized"}',
                        status_code=401,
                        headers={"WWW-Authenticate": "Basic"},
                        media_type="application/json"
                    )
                
                # Handle root
                if full_path == '' or full_path == '/':
                    if request.method == 'POST':
                        return await super(BlackjackDealer, self)._handle_root_request(request)
                    else:
                        bot_dir = Path(__file__).parent
                        web_root = bot_dir.parent / 'web'
                        index_file = web_root / 'client' / 'index.html'
                        return self._serve_static_file(index_file)
                
                # Handle /blackjack endpoint - return SWML
                if full_path == 'blackjack' or full_path == 'blackjack/':
                    return await super(BlackjackDealer, self)._handle_root_request(request)
                
                # Handle known SWML endpoints
                clean_path = full_path.rstrip("/")
                if clean_path == "debug":
                    return await self._handle_debug_request(request)
                elif clean_path == "swaig":
                    return await self._handle_swaig_request(request, Response())
                elif clean_path == "post_prompt":
                    return await self._handle_post_prompt_request(request)
                elif clean_path == "check_for_input":
                    return await self._handle_check_for_input_request(request)
                
                # Try to serve static files
                bot_dir = Path(__file__).parent
                web_root = bot_dir.parent / 'web'
                
                # Try web/client first
                client_file = web_root / 'client' / full_path
                if client_file.exists() and client_file.is_file():
                    return self._serve_static_file(client_file)
                
                # Try web root
                web_file = web_root / full_path
                if web_file.exists() and web_file.is_file():
                    return self._serve_static_file(web_file)
                
                # File not found
                return {"error": "File not found"}
            
            self._app = app
        
        host = host or self.host
        port = port or self.port
        
        # Print startup info
        username, password = self.get_basic_auth_credentials()
        print(f"Agent '{self.name}' is available at:")
        print(f"URL: http://localhost:{port}")
        print(f"Basic Auth: {username}:{password} (source: provided)")
        
        # Run the server
        uvicorn.run(self._app, host=host, port=port)


def main():
    """Run the Blackjack Dealer"""
    import sys
    
    # Check if we're being run by swaig-test or as a module
    is_swaig_test = any('swaig-test' in arg or 'test_swaig' in arg for arg in sys.argv)
    
    # If run by swaig-test, return the agent instance for testing
    if is_swaig_test:
        return BlackjackDealer()
    
    # Normal standalone execution
    parser = argparse.ArgumentParser(
        description='Blackjack Dealer - SignalWire Casino Game',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  python3 sigmond_blackjack.py                # Run on default port 5000
  python3 sigmond_blackjack.py --port 8080    # Run on port 8080
        """
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=int(os.environ.get('PORT', 5000)),
        help='Port to run the agent on (default: 5000 or $PORT)'
    )
    
    args = parser.parse_args()
    port = args.port
    
    print("=" * 60)
    print("🎰 Blackjack Dealer - SignalWire Casino")
    print("=" * 60)
    print()
    print("A professional blackjack dealer ready to deal you in!")
    print()
    print("Starting chips: 1000")
    print("Minimum bet: 10 chips")
    print("Dealer rules: Hits on 16, Stands on 17")
    print()
    
    # Create and run dealer
    dealer = BlackjackDealer()
    
    # Get auth credentials
    username, password = dealer.get_basic_auth_credentials()
    
    # Create our own FastAPI app for better control over routing
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    
    app = FastAPI(redirect_slashes=False)
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Set up static file serving for the web client FIRST (before agent routes)
    web_dir = Path(__file__).parent.parent / "web"
    client_dir = web_dir / "client"
    
    # Add static file routes WITHOUT authentication
    if True:
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse, HTMLResponse
        
        # Mount the web directories
        if web_dir.exists():
            # Mount card images at /card_images
            card_images_dir = web_dir / "card_images"
            if card_images_dir.exists():
                app.mount("/card_images", StaticFiles(directory=str(card_images_dir)), name="card_images")
            
            # Add individual routes for media files (no auth required)
            @app.get("/sigmond_bj_idle.mp4")
            async def get_idle_video():
                video_path = web_dir / "sigmond_bj_idle.mp4"
                if video_path.exists():
                    return FileResponse(str(video_path), media_type="video/mp4")
                return {"error": "File not found"}
            
            @app.get("/sigmond_bj_talking.mp4")
            async def get_talking_video():
                video_path = web_dir / "sigmond_bj_talking.mp4"
                if video_path.exists():
                    return FileResponse(str(video_path), media_type="video/mp4")
                return {"error": "File not found"}
            
            @app.get("/casino.mp3")
            async def get_casino_audio():
                audio_path = web_dir / "casino.mp3"
                if audio_path.exists():
                    return FileResponse(str(audio_path), media_type="audio/mpeg")
                return {"error": "File not found"}
            
            # Serve client files at root (no auth required)
            @app.get("/")
            async def serve_index():
                index_path = client_dir / "index.html"
                if index_path.exists():
                    return FileResponse(str(index_path), media_type="text/html")
                return {"error": "Client not found"}
            
            @app.get("/app.js")
            async def serve_app_js():
                js_path = client_dir / "app.js"
                if js_path.exists():
                    return FileResponse(str(js_path), media_type="application/javascript")
                return {"error": "app.js not found"}
            
            @app.get("/signalwire.js")
            async def serve_signalwire_js():
                js_path = client_dir / "signalwire.js"
                if js_path.exists():
                    return FileResponse(str(js_path), media_type="application/javascript")
                return {"error": "signalwire.js not found"}
            
            # Serve favicon
            @app.get("/favicon.svg")
            async def serve_favicon_svg():
                favicon_path = client_dir / "favicon.svg"
                if favicon_path.exists():
                    return FileResponse(str(favicon_path), media_type="image/svg+xml")
                return {"error": "favicon.svg not found"}
            
            @app.get("/favicon.ico")
            async def serve_favicon_ico():
                # Serve SVG as fallback for .ico requests
                favicon_path = client_dir / "favicon.svg"
                if favicon_path.exists():
                    return FileResponse(str(favicon_path), media_type="image/svg+xml")
                return {"error": "favicon not found"}
            
            # Serve Open Graph image for social media previews
            @app.get("/og-image.png")
            @app.get("/og-image.svg")
            async def serve_og_image():
                og_image_path = web_dir / "og-image.svg"
                if og_image_path.exists():
                    return FileResponse(str(og_image_path), media_type="image/svg+xml",
                                      headers={
                                          "Cache-Control": "public, max-age=86400",  # Cache for 1 day
                                          "Content-Type": "image/svg+xml"
                                      })
                return {"error": "og-image not found"}
    
    # Now add the agent's routes (these will require auth)
    router = dealer.as_router()
    app.include_router(router, prefix="/blackjack")
    
    # Add a redirect from /blackjack to /blackjack/ for both GET and POST
    from fastapi.responses import RedirectResponse
    
    @app.get("/blackjack")
    async def redirect_to_blackjack_slash_get():
        return RedirectResponse(url="/blackjack/", status_code=307)
    
    @app.post("/blackjack")
    async def redirect_to_blackjack_slash_post():
        return RedirectResponse(url="/blackjack/", status_code=307)
    
    
    # Store the app in the dealer instance so it can be used
    dealer._app = app
    
    print(f"Web client available at: http://localhost:{port}/")
    print(f"SWML endpoint available at: http://localhost:{port}/blackjack")
    print(f"Basic Auth required for /blackjack: {username}:{password}")
    print()
    print(f"Starting Dealer on port {port}... Press Ctrl+C to stop.")
    print("=" * 60)
    
    try:
        # Run using uvicorn directly with our custom app
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=port)
    except KeyboardInterrupt:
        print("\n🎰 Thanks for playing! The casino is now closed.")


if __name__ == "__main__":
    main()
