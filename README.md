
# TODO:

- [x] MCP client module 
    - responsible for making HTTP requests to the MCP server
- [x] config
    - [x] mcp server
- [x] task/game state and data
    - [x] start page
    - [x] end page
    - [x] current page
    - [x] page history (number of stepsis implicit here)
    - [x] time elapsed
    - [x] result (success/failure)
- [x] LLM abstraction layer for multi-provider support
    - [x] base class
    - read the documentation for the providers and determine the settings each needs
    - [x] abstract list tools method
        - need to convert to function definition format for each provider
    - [x] anthropic model
    - [x] openai model

# idea
Turn the wikipedia game into an eval / training environment for Language Models

score is number of moves 
- link clicks or back buttons

great for evaluating thinking models
- teaching MCP

easy way to directly compare models on the same exact task
- means we can have an ELO system
- models can do 1v1s

gives us a way to compare _speed_ of model
- reasoning models take a lot longer
and measure the infrastructure
- API rate limits from Anthropic etc can be taken into account

can be a training environment too
- great RL env with verifiable rewards
- teaches them to reach multi-step goals where not all steps can be planned from initial state
## text based version
### simple
only put all the links in context
### hard
append the entire article in context
- evaluate long context
## computer use version
would require scrolling and clicking links

my theory is that learning very general tasks like this could train general remote worker skills
- scrolling web pages
- clicking links
- understanding internet structure
# why
to learn how to make evals / RL envs
to learn MCP
has a human baseline
- eventually this would be 
# goal
create a eval where LLMs can race through Wikipedia 

create an elo system to compare models based on speed
- have different 'ranked' modes

- create cool graph visuals of attempts
	- distance from goal


## stretch goal
man vs machine
play 1v1 in real time vs language model

allows us to benchmark machine vs human performance 

# game
https://en.wikipedia.org/wiki/Wikipedia:Wiki_Game
> In a Wikipedia race, you and your friends can race for one of two objectives:
1. Get to the end page as fast as possible
2. Get to the end page in the fewest number of clicks

I think [[#elo]] should be based on (1) instead of (2). 2 can be another metric for optimality

## rules
no back button
- clear the context (other than sys prompt) when pre-filling the next page
- how do I prevent the model from reward hacking and just typing the memorized destination link? can I enforce that the link must be in the current page somehow?
	- this would allow me to not delete the previous page from context

timing
remove MCP time (wikipedia page loads and parsing)

only count inference time on API for provider

# features
## elo
two versions
- time based
- step based

can we compare any two attempts on the same task (start/end pair)?
what about multiple?
I think so

### difficulty
graph model performance based on task difficulty
- we could do many runs on same task to have individual task distributions 
- then just aggregate for [[central limit theorem]] distribution 


simplest version is based on number of steps
but ones with multiple paths are “easier”
discoverability matters too. larger pages with only a single optimal link

## interactive viewing experience 
humans can watch models compete
see and scroll on pages that models are on
see thinking (CoT or reasoning)

### live graph
shows current and shortest paths to goal for each current model 

all models start at same initial node 
as they step we recalculate shortest path to goal from new node

allows you to see which ones are ahead live and optimal / neutral / bad moves
- we could color code these nodes relatively
	-  or do we color the edge? we could change size of edge or node relative to time spent 
- there are multiple layers of bad since theoretically a move can make you 2+ away
### replay
fake the scrolling on page and clicking on link
chat replay
graph replay
## man vs machine (or man)
live graph of competitors visible

use this data to tune human benchmark on task benchmark 

humans may cheat tho

## wall of shame
show all examples of players cheating by selecting a next page that is not accessible from the current page

“leaderboard” for most cheating attempts / rate
