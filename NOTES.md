# Notes on Experimentations

Before running anything with RAG I took a baseline of the model's capabilities. 

Qwen3:8b's thinking mode aboslutely freaked out and it also took FOREVER to run so I killed it and couldn't take a baseline. Will have to go back and test a smaller size and if I can disable thinking somehow with better prompting or see if the RAG can help it not hallucinate itself in an endless loop. 

Here was the `mistral:7b` run, much better. A simple query asking about wargear. It's specific enough that someone with knowledge of the codex (or the codex right in front of them) could get it right. But open ended enough that there's options for hallucination or just misinterpretations.

> What wargear is available for Tactical Marines in Warhammer 40k 9th edition?

```bash
smr@caliban:~$ ollama run mistral:7b
>>> What wargear is available for Tactical Marines in Warhammer 40k 9th edition?
 In Warhammer 40k 9th Edition, Tactical Marines from the Adeptus Astartes have a variety of wargear options to 
customize their units. Here are some common choices:

1. **Bolter**: The standard weapon for Tactical Marines, capable of firing rapid bursts of bolter rounds at enemies.

2. **Chainfed Stormbolter**: A heavy bolter mounted on a bipod that allows multiple Marines to fire it with the 
Chain-Cannon rule.

3. **Flamestorm Grenade Launcher**: Fires incendiary grenades, causing S8 AP-2 D6 damage and setting enemies on fire.

4. **Heavy Bolter**: A heavy weapon that fires large bolts at high velocity, capable of inflicting heavy damage against 
hordes.

5. **Missile Launcher**: Fires powerful missiles with high strength, AP, and damage, making it effective against tough 
targets like vehicles and monsters.

6. **Plasma Gun**: An energy weapon that fires hot plasma, causing S9 AP-3 D3 damage and ignoring cover saves on a roll 
of 6 to wound.

7. **Meltagun**: Fires superheated molten metal, causing S10 AP-4 D1 damage against vehicles and making all hits 
against the target automatic crits if they score a wound.

8. **Power Fist**: A close combat weapon that allows Marines to fight in melee with increased strength and damage 
potential.

9. **Power Sword**: A close combat weapon that allows Marines to make precision attacks, re-rolling hit rolls of 1 and 
wound rolls of 6.

10. **Combi-weapons**: These are hybrid weapons that can be configured to fire either bolter or special ammunition 
(like plasma, meltagun, or flamer).

In addition to these weapons, Tactical Marines also have access to various special equipment like frag and krak 
grenades, bolter magazines, combi-melta, combi-plasma, jump packs, and more. They can also take Sergeant upgrades with 
options for artificer armor, power weapon, or relic blade. Lastly, they can take a Chapter Tactics upgrade to reflect 
the unique tactics of their Space Marine Chapter.
```

Pretty good honestly. I wonder if I ask about specific point values for these, what that would look like?

> What wargear is available for Tactical Marines in Warhammer 40k 9th edition? What are the points values for those items and the limits that can be taken.

```bash
>>> What wargear is available for Tactical Marines in Warhammer 40k 9th edition? What are the points values for those items a
... nd the limits that can be taken.
 Here's a list of some common wargear options for Tactical Marines in Warhammer 40k 9th Edition, along with their 
current point costs (as per the Warhammer Community dataslate - Battle for Prospero) and limits on how many can be 
taken per squad:

1. **Bolter**: Base weapon, no points cost. A squad of 5-10 Tactical Marines comes equipped with these as standard.

2. **Chainfed Stormbolter**: Heavy weapon, 20 points. One model in the squad can take it, and a maximum of two models 
can be equipped with any combination of heavy weapons per squad.

3. **Flamestorm Grenade Launcher**: Special weapon, 5 points. One model in the squad can take it, and a maximum of two 
models can be equipped with special weapons per squad (excluding combi-weapons).

4. **Heavy Bolter**: Heavy weapon, 15 points. One model in the squad can take it, and a maximum of two models can be 
equipped with any combination of heavy weapons per squad.

5. **Missile Launcher**: Heavy weapon, 20 points. One model in the squad can take it, and a maximum of two models can 
be equipped with special weapons or any combination of heavy weapons per squad (excluding combi-weapons).

6. **Plasma Gun**: Special weapon, 15 points. One model in the squad can take it, and a maximum of two models can be 
equipped with special weapons or any combination of heavy weapons per squad (excluding combi-weapons).

7. **Meltagun**: Heavy weapon, 15 points. One model in the squad can take it, and a maximum of two models can be 
equipped with special weapons or any combination of heavy weapons per squad (excluding combi-weapons).

8. **Power Fist**: Close combat weapon, 10 points. One model in the squad can take it, and no more than three models 
can have power weapons in a squad of 5-10 Marines.

9. **Power Sword**: Close combat weapon, 10 points. One model in the squad can take it, and no more than three models 
can have power weapons in a squad of 5-10 Marines.

10. **Combi-weapons**: These hybrid weapons are counted as both boltguns and the special or heavy weapon they're 
configured to fire. Points cost varies based on the specific combi-weapon:
        * Combi-bolter: No points cost, functions as a boltgun in shooting phase.
        * Combi-melta: Heavy weapon, 10 points, fires as a melta gun.
        * Combi-plasma: Special weapon, 5 points, fires as a plasma gun.
11. **Frag and Krak grenades**: Free of charge. One model in the squad can take up to 3 frag grenades and 3 krak 
grenades.

12. **Bolter magazine (Bolt Pistol and Grenade Harness)**: These are optional equipment for Tactical Marines that cost 
no additional points. A Marine armed with a bolt pistol can also take a bolter magazine, which allows him to carry 6 
extra rounds for his bolter instead of the usual 10.

13. **Jump Pack**: Elite weapon, 25 points. One model in the squad can take it (excluding the Sergeant). A maximum of 
three models can have jump packs in a squad of 5-10 Marines.

14. **Chapter Tactics**: This is not actual wargear but represents unique abilities specific to a Space Marine Chapter. 
Each Chapter has its own unique tactics, such as the Ultramarines' Vigilus Detachment or the Salamanders' Fires of 
Prospero. These don't have a points cost and can be applied to any unit in your army.

```