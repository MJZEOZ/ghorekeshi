import random

def pick_winners(users, prizes):

    winners = []

    shuffled = users.copy()
    random.shuffle(shuffled)

    for i, prize in enumerate(prizes):
        if i < len(shuffled):
            winners.append({
                "user": shuffled[i],
                "prize": prize
            })

    return winners
