# Killchain weapons

Generated from `src/arsenal.rs` in RedEngine (`cargo run --example weapons_table`). Damage is per hit to the body; the headshot column is the multiplier.

| Weapon | Real counterpart | Damage | Head x | Rounds/min | Mag / reserve | Reload s | Auto | Range m |
|---|---|---|---|---|---|---|---|---|
| R9 service pistol | Glock 17, 9x19 mm | 28 | 4 | 450 | 17 / 68 | 2.2 | false | 90.0 |
| Viper machine pistol | Glock 18, 9x19 mm | 19 | 3.5 | 900 | 33 / 99 | 2.3 | true | 70.0 |
| Ember SMG | H&K MP5, 9x19 mm | 25 | 4 | 720 | 30 / 120 | 2.3 | true | 100.0 |
| Rook carbine | Colt M4A1, 5.56x45 mm | 32 | 4 | 720 | 30 / 90 | 2.4 | true | 160.0 |
| Redline rifle | AK-47, 7.62x39 mm | 36 | 4 | 600 | 30 / 90 | 2.5 | true | 160.0 |
| Kestrel bullpup | Steyr AUG, 5.56x45 mm | 30 | 4 | 720 | 30 / 90 | 3 | true | 170.0 |
| Longbow marksman rifle | M14 EBR, 7.62x51 mm | 52 | 3.5 | 300 | 10 / 40 | 2.6 | false | 220.0 |
| Breach shotgun | Mossberg 500, 12 gauge | 160 (9 pellets) | 1.5 | 71 | 8 / 32 | 0.5 | false | 40.0 |
| Atlas LMG | FN M249 SAW, 5.56x45 mm | 30 | 4 | 900 | 100 / 200 | 5.6 | true | 170.0 |
| Warden scout rifle | Steyr Scout, 7.62x51 mm | 88 | 2.8 | 52 | 10 / 40 | 3 | false | 320.0 |
| Bulldog .45 | Colt M1911, .45 ACP | 36 | 4 | 360 | 8 / 40 | 2 | false | 90.0 |
| Hand Cannon .50 | IMI Desert Eagle, .50 AE | 58 | 3.5 | 164 | 7 / 35 | 2.3 | false | 100.0 |
| Marshal .357 | Colt Python, .357 Magnum | 52 | 3.5 | 144 | 6 / 36 | 3 | false | 110.0 |
| Stinger SMG | H&K UMP45, .45 ACP | 32 | 4 | 600 | 25 / 100 | 2.5 | true | 100.0 |
| Ranger PDW | FN P90, 5.7x28 mm | 24 | 4 | 900 | 50 / 100 | 3.3 | true | 110.0 |
| Wasp SMG | KRISS Vector, .45 ACP | 23 | 4 | 1200 | 33 / 99 | 2.1 | true | 90.0 |
| Ironside battle rifle | FN SCAR-H, 7.62x51 mm | 40 | 4 | 514 | 20 / 60 | 2.8 | true | 180.0 |
| Gale sniper | H&K G3SG/1, 7.62x51 mm | 78 | 3 | 225 | 20 / 60 | 3.3 | false | 300.0 |
| Sentinel .338 | AI L115A3, .338 Lapua | 118 | 4 | 41 | 5 / 25 | 3.6 | false | 400.0 |
| Auto-12 shotgun | Benelli M4, 12 gauge | 120 (6 pellets) | 1.5 | 257 | 7 / 35 | 0.42 | false | 36.0 |
| Coach gun | Sawed-off double-barrel, 12 gauge | 190 (12 pellets) | 1.5 | 277 | 2 / 16 | 2.4 | false | 28.0 |
| Hammer MG | IWI Negev, 5.56x45 mm | 28 | 4 | 900 | 150 / 150 | 5.8 | true | 160.0 |
| Lancer rocket launcher | RPG-7, 40 mm rocket | 90 | 1 | 60 | 1 / 3 | 4 | false | 200.0 |
| Thumper grenade launcher | M79 grenade launcher, 40x46 mm | 70 | 1 | 86 | 1 / 8 | 2.4 | false | 120.0 |
| Reaper minigun | GAU-19 rotary gun, 7.62x51 mm (tuned for a person to carry) | 18 | 3.5 | 1200 | 200 / 200 | 7.5 | true | 150.0 |
| Breaker slug gun | Mossberg 500 firing foster slugs, 12 gauge | 80 | 1.5 | 71 | 6 / 24 | 0.5 | false | 90.0 |
| Hunter crossbow | recurve crossbow, 400-grain bolt | 85 | 2 | 60 | 1 / 15 | 2 | false | 120.0 |
| Flare gun | Orion signal pistol, 26.5 mm flare | 30 | 1 | 75 | 1 / 5 | 1.8 | false | 100.0 |
| Lobber mortar | 60 mm light mortar, hand-held | 60 | 1 | 67 | 2 / 8 | 3.2 | false | 150.0 |

## Melee
| Weapon | Real counterpart | Damage | Swing s | Reach m |
|---|---|---|---|---|
| baseball bat | baseball bat | 48 | 0.85 | 2.3 |
| combat knife | combat knife | 40 (backstab kills) | 0.45 | 2 |
| camp hatchet | camp hatchet | 55 | 0.75 | 2.1 |
| machete | machete | 52 | 0.55 | 2.2 |
| sledgehammer | sledgehammer | 100 (one hit kills) | 1.5 | 2.3 |

## Grenades
| Weapon | Real counterpart | Fuse s | Radius m | Blast damage | Lasts s |
|---|---|---|---|---|---|
| frag grenade | M67 fragmentation grenade | 1.9 | 7 | 105 |  |
| flashbang | M84 stun grenade | 1.5 | 22 |  | 5 |
| smoke grenade | M18 smoke grenade | 1.3 | 4.6 |  | 18 |
| incendiary grenade | M14 incendiary grenade | 1.4 | 3.6 | 28 per tick | 7 |
| impact grenade | M25 impact grenade | on contact | 4.2 | 80 |  |
