import math
import random
import sys
from typing import List

import pygame

# ---------------------------
# Config & Helpers
# ---------------------------
VIRTUAL_W, VIRTUAL_H = 960, 540  # base canvas; will scale to window
FPS = 120

WHITE = (240, 240, 240)
BLACK = (10, 10, 12)
GRAY = (80, 80, 90)
RED = (230, 70, 80)
GREEN = (60, 210, 120)
BLUE = (90, 160, 255)
YELLOW = (250, 220, 90)
ORANGE = (255, 160, 70)
PURPLE = (200, 120, 255)
CYAN = (120, 240, 240)

random.seed()



def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def vec_from_angle(theta):
    return math.cos(theta), math.sin(theta)


# ---------------------------
# Camera for screen shake
# ---------------------------
class Camera:
    def __init__(self):
        self.offset = pygame.Vector2(0, 0)
        self.shake_mag = 0.0

    def update(self, dt):
        if self.shake_mag > 0:
            self.offset.x = random.uniform(-self.shake_mag, self.shake_mag)
            self.offset.y = random.uniform(-self.shake_mag, self.shake_mag)
            self.shake_mag = max(0.0, self.shake_mag - 60 * dt)  # decay
        else:
            self.offset.xy = (0, 0)

    def shake(self, amount):
        self.shake_mag = max(self.shake_mag, amount)


# ---------------------------
# Particles
# ---------------------------
class Particle:
    def __init__(self, pos, vel, life, size, color):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.life = life
        self.max_life = life
        self.size = size
        self.color = color

    def update(self, dt):
        self.pos += self.vel * dt
        self.vel *= 0.98
        self.life -= dt
        return self.life > 0

    def draw(self, surf, camera):
        alpha = clamp(int(255 * (self.life / self.max_life)), 0, 255)
        c = (*self.color, alpha)
        pygame.draw.circle(surf, c, (self.pos + camera.offset), self.size)


# ---------------------------
# Barrier / simple rect collider (blocks player & enemies)
# ---------------------------
class Barrier:
    def __init__(self, rect: pygame.Rect):
        self.rect = rect

    def draw(self, surf, camera):
        r = self.rect.move(camera.offset)
        pygame.draw.rect(surf, (28, 30, 40), r, border_radius=6)
        pygame.draw.rect(surf, (50, 55, 70), r, 2, border_radius=6)

    @staticmethod
    def resolve_circle_collision(center: pygame.Vector2, radius: float, rect: pygame.Rect):
        # Closest point on rect to the circle center
        cx = clamp(center.x, rect.left, rect.right)
        cy = clamp(center.y, rect.top, rect.bottom)
        dx = center.x - cx
        dy = center.y - cy
        dist_sq = dx * dx + dy * dy
        if dist_sq < radius * radius:
            dist = math.sqrt(dist_sq) if dist_sq > 1e-6 else 0.0
            if dist == 0:
                # push out in the smallest axis direction
                # choose axis with smaller penetration
                left_pen = abs(center.x - rect.left)
                right_pen = abs(rect.right - center.x)
                top_pen = abs(center.y - rect.top)
                bottom_pen = abs(rect.bottom - center.y)
                min_pen = min(left_pen, right_pen, top_pen, bottom_pen)
                if min_pen == left_pen:
                    center.x = rect.left - radius
                elif min_pen == right_pen:
                    center.x = rect.right + radius
                elif min_pen == top_pen:
                    center.y = rect.top - radius
                else:
                    center.y = rect.bottom + radius
            else:
                nx, ny = dx / dist, dy / dist
                # move out to the surface
                center.x = cx + nx * (radius + 0.01)
                center.y = cy + ny * (radius + 0.01)
            return True
        return False


# ---------------------------
# Entities
# ---------------------------
class Bullet:
    def __init__(self, pos, vel, color=YELLOW, radius=3, dmg=1, pierce=0):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.color = color
        self.radius = radius
        self.alive = True
        self.dmg = dmg
        self.pierce = pierce

    def update(self, dt):
        self.pos += self.vel * dt
        if not (-50 < self.pos.x < VIRTUAL_W + 50 and -50 < self.pos.y < VIRTUAL_H + 50):
            self.alive = False

    def draw(self, surf, camera):
        pygame.draw.circle(surf, self.color, (self.pos + camera.offset), self.radius)


class Enemy:
    def __init__(self, kind: str, pos):
        self.kind = kind
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(0, 0)
        if kind == "chaser":
            self.speed = random.uniform(70, 95)   # slightly slower (easier early)
            self.hp = 2
            self.radius = 14
            self.color = ORANGE
            self.damage = 10
        elif kind == "sprinter":
            self.speed = random.uniform(120, 160)
            self.hp = 1
            self.radius = 10
            self.color = CYAN
            self.damage = 8
        else:  # tank
            self.speed = random.uniform(50, 65)
            self.hp = 4
            self.radius = 18
            self.color = PURPLE
            self.damage = 16
        self.alive = True

    def update(self, dt, player_pos, barriers: List[Barrier]):
        dir = (player_pos - self.pos)
        dist = dir.length() + 1e-5
        dir = dir / dist
        self.vel = dir * self.speed
        self.pos += self.vel * dt
        # collide with barriers
        for b in barriers:
            Barrier.resolve_circle_collision(self.pos, self.radius, b.rect)

    def hit(self, dmg):
        self.hp -= dmg
        if self.hp <= 0:
            self.alive = False

    def draw(self, surf, camera):
        pygame.draw.circle(surf, self.color, (self.pos + camera.offset), self.radius)
        eye_dir = self.vel.normalize() if self.vel.length_squared() > 0 else pygame.Vector2(1, 0)
        eye_pos = self.pos + eye_dir * (self.radius * 0.6)
        pygame.draw.circle(surf, BLACK, (eye_pos + camera.offset), max(2, int(self.radius * 0.15)))


class Player:
    def __init__(self, pos):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(0, 0)
        self.speed = 210
        self.base_speed = 210
        self.radius = 14
        self.color = WHITE
        self.hp = 100
        self.max_hp = 100
        self.invuln = 0.0
        self.shield = 0.0
        self.combo = 1.0
        self.combo_time = 0.0
        self.score = 0
        self.high_score = 0
        self.fire_cd = 0.18
        self.fire_timer = 0.0
        self.rapid_timer = 0.0
        self.spread_timer = 0.0

    def update(self, dt, keys, mouse_pos, barriers: List[Barrier]):
        move = pygame.Vector2(0, 0)
        if keys[pygame.K_UP]:
            move.y -= 1
        if keys[pygame.K_DOWN]:
            move.y += 1
        if keys[pygame.K_LEFT]:
            move.x -= 1
        if keys[pygame.K_RIGHT]:
            move.x += 1
        if move.length_squared() > 0:
            move = move.normalize()
        cur_speed = self.base_speed + (120 if self.rapid_timer > 0 else 0)
        cur_speed += (120 if self.spread_timer > 0 else 0)
        if self.shield > 0:
            cur_speed -= 20
        self.vel = move * max(120, self.speed if self.rapid_timer <= 0 else cur_speed)
        # attempt move with barrier resolution (simple: move then push out)
        self.pos += self.vel * dt
        self.pos.x = clamp(self.pos.x, 16, VIRTUAL_W - 16)
        self.pos.y = clamp(self.pos.y, 16, VIRTUAL_H - 16)
        for b in barriers:
            Barrier.resolve_circle_collision(self.pos, self.radius, b.rect)

        # timers
        self.invuln = max(0.0, self.invuln - dt)
        self.rapid_timer = max(0.0, self.rapid_timer - dt)
        self.spread_timer = max(0.0, self.spread_timer - dt)
        if self.combo_time > 0:
            self.combo_time = max(0.0, self.combo_time - dt)
            if self.combo_time == 0:
                self.combo = 1.0

    def can_shoot(self):
        return self.fire_timer <= 0.0

    def reset_cooldown(self):
        base = 0.18
        if self.rapid_timer > 0:
            base *= 0.45
        self.fire_cd = base
        self.fire_timer = self.fire_cd

    def tick_cooldown(self, dt):
        self.fire_timer = max(0.0, self.fire_timer - dt)

    def damage(self, dmg):
        if self.invuln > 0:
            return False
        if self.shield > 0:
            self.shield = 0.0
            self.invuln = 0.15
            return True
        self.hp -= dmg
        self.invuln = 0.2
        return True

    def heal(self, amount):
        self.hp = min(self.max_hp, self.hp + amount)

    def add_score(self, base):
        gained = int(base * self.combo)
        self.score += gained
        self.high_score = max(self.high_score, self.score)
        self.combo = min(5.0, self.combo + 0.1)
        self.combo_time = 3.0
        return gained

    def draw(self, surf, camera, mouse_pos):
        color = self.color
        if self.invuln > 0 and int(self.invuln * 40) % 2 == 0:
            color = GRAY
        pygame.draw.circle(surf, color, (self.pos + camera.offset), self.radius)
        aim = (pygame.Vector2(mouse_pos) - self.pos)
        angle = math.atan2(aim.y, aim.x)
        tip = self.pos + pygame.Vector2(math.cos(angle), math.sin(angle)) * (self.radius + 6)
        left = self.pos + pygame.Vector2(math.cos(angle + 2.6), math.sin(angle + 2.6)) * (self.radius - 2)
        right = self.pos + pygame.Vector2(math.cos(angle - 2.6), math.sin(angle - 2.6)) * (self.radius - 2)
        pygame.draw.polygon(surf, BLUE if self.shield > 0 else YELLOW, [tip + camera.offset, left + camera.offset, right + camera.offset], 2)


# ---------------------------
# Game
# ---------------------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Top‑Down Shooter — Survival")
        self.window = pygame.display.set_mode((VIRTUAL_W, VIRTUAL_H), pygame.RESIZABLE | pygame.DOUBLEBUF)
        self.surface = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
        self.clock = pygame.time.Clock()

        self.camera = Camera()
        self.player = Player((VIRTUAL_W / 2, VIRTUAL_H / 2))

        self.bullets: List[Bullet] = []
        self.enemies: List[Enemy] = []
        self.particles: List[Particle] = []
        self.barriers: List[Barrier] = []

        self.level = 1
        self.level_time_left = self.goal_time_for(self.level)
        self.time = 0.0
        self.spawn_timer = 0.0

        # states: menu, playing, paused, cleared, gameover
        self.state = "menu"
        self.bg_t = 0.0
        self.flash = 0.0

        self.setup_level(self.level, reset_player=True, refill_hp=True)

    # ---------- Level helpers ----------
    def goal_time_for(self, lvl: int) -> float:
        # slightly longer with each level
        return 18 + (lvl - 1) * 4

    def spawn_rate_for(self, lvl: int) -> float:
        # higher level -> faster spawns (smaller interval)
        return max(0.9 - (lvl - 1) * 0.08, 0.35)

    def barrier_layout_for(self, lvl: int) -> List[Barrier]:
        random.seed(lvl * 1337)
        bars: List[Barrier] = []
        # simple patterns that change with level
        pad = 60
        w, h = VIRTUAL_W - pad * 2, VIRTUAL_H - pad * 2
        # central blocks
        count = 2 + (lvl % 3)
        for i in range(count):
            bw = random.randint(90, 140)
            bh = random.randint(28, 46)
            x = pad + random.randint(0, max(1, w - bw))
            y = pad + random.randint(0, max(1, h - bh))
            bars.append(Barrier(pygame.Rect(x, y, bw, bh)))
        # side walls (thin) that create lanes on some levels
        if lvl % 2 == 0:
            bars.append(Barrier(pygame.Rect(VIRTUAL_W//2 - 12, pad, 24, VIRTUAL_H - pad*2)))
        if lvl % 3 == 0:
            bars.append(Barrier(pygame.Rect(pad, VIRTUAL_H//2 - 12, VIRTUAL_W - pad*2, 24)))
        return bars

    def setup_level(self, lvl: int, reset_player: bool, refill_hp: bool):
        self.enemies.clear()
        self.bullets.clear()
        self.particles.clear()
        self.barriers = self.barrier_layout_for(lvl)
        self.level = lvl
        self.level_time_left = self.goal_time_for(lvl)
        self.time = 0.0
        self.spawn_timer = 0.0
        if reset_player:
            self.player.pos.update(VIRTUAL_W / 2, VIRTUAL_H / 2)
            self.player.vel.update(0, 0)
        if refill_hp:
            self.player.hp = self.player.max_hp
        self.flash = 0.0

    # ---------- Utility ----------
    def world_mouse(self):
        win_w, win_h = self.window.get_size()
        scale = min(win_w / VIRTUAL_W, win_h / VIRTUAL_H)
        surf_w, surf_h = int(VIRTUAL_W * scale), int(VIRTUAL_H * scale)
        x_off = (win_w - surf_w) // 2
        y_off = (win_h - surf_h) // 2
        mx, my = pygame.mouse.get_pos()
        return ((mx - x_off) / scale, (my - y_off) / scale)

    def spawn_enemy(self):
        margin = 40
        side = random.choice(["top", "bottom", "left", "right"])
        if side == "top":
            pos = (random.uniform(0, VIRTUAL_W), -margin)
        elif side == "bottom":
            pos = (random.uniform(0, VIRTUAL_W), VIRTUAL_H + margin)
        elif side == "left":
            pos = (-margin, random.uniform(0, VIRTUAL_H))
        else:
            pos = (VIRTUAL_W + margin, random.uniform(0, VIRTUAL_H))
        r = random.random()
        spr_prob = clamp(0.10 + self.level * 0.01, 0.10, 0.30)
        tank_prob = clamp(0.07 + self.level * 0.008, 0.07, 0.22)
        if r < spr_prob:
            kind = "sprinter"
        elif r < spr_prob + tank_prob:
            kind = "tank"
        else:
            kind = "chaser"
        self.enemies.append(Enemy(kind, pos))

    # ---------- Effects ----------
    def add_explosion(self, pos, base_color):
        for _ in range(20):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(40, 220)
            vel = (math.cos(ang) * spd, math.sin(ang) * spd)
            life = random.uniform(0.2, 0.6)
            size = random.randint(2, 4)
            self.particles.append(Particle(pos, vel, life, size, base_color))
        self.camera.shake(6)
        self.flash = 0.2

    def add_muzzle(self, pos, angle):
        for _ in range(6):
            spd = random.uniform(60, 220)
            jitter = angle + random.uniform(-0.2, 0.2)
            vel = (math.cos(jitter) * spd, math.sin(jitter) * spd)
            life = random.uniform(0.05, 0.2)
            size = random.randint(1, 2)
            self.particles.append(Particle(pos, vel, life, size, YELLOW))
        self.camera.shake(2.5)

    # ---------- Game Loop ----------
    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self.bg_t += dt

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.state == "playing":
                            self.state = "paused"
                        elif self.state == "paused":
                            self.state = "playing"
                    if event.key == pygame.K_RETURN:
                        if self.state == "menu":
                            self.state = "playing"
                        elif self.state == "gameover":
                            self.__init__()
                        elif self.state == "cleared":
                            # ENTER -> next level
                            self.setup_level(self.level + 1, reset_player=True, refill_hp=True)
                            self.state = "playing"
                    if self.state == "cleared":
                        if event.key == pygame.K_n:
                            self.setup_level(self.level + 1, reset_player=True, refill_hp=True)
                            self.state = "playing"
                        if event.key == pygame.K_r:
                            self.setup_level(self.level, reset_player=True, refill_hp=True)
                            self.state = "playing"
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if self.state == "menu":
                        self.state = "playing"

            if self.state == "menu":
                self.draw_menu()
                self.blit_to_window()
                continue
            elif self.state == "paused":
                self.draw_scene(paused=True)
                self.blit_to_window()
                continue
            elif self.state == "gameover":
                self.draw_gameover()
                self.blit_to_window()
                continue
            elif self.state == "cleared":
                self.draw_scene()
                self.draw_cleared()
                self.blit_to_window()
                continue

            # playing
            self.update(dt)
            self.draw_scene()
            self.blit_to_window()

    # ---------- Update ----------
    def update(self, dt):
        self.camera.update(dt)
        mouse_world = pygame.Vector2(self.world_mouse())
        keys = pygame.key.get_pressed()

        # Count down survival timer
        self.level_time_left = max(0.0, self.level_time_left - dt)
        if self.level_time_left == 0.0:
            # SUCCESS: stop the action & prompt
            self.state = "cleared"
            return

        # Player update
        self.player.update(dt, keys, mouse_world, self.barriers)
        self.player.tick_cooldown(dt)

        # Shooting
        if pygame.mouse.get_pressed()[0] and self.player.can_shoot():
            aim = mouse_world - self.player.pos
            if aim.length_squared() > 1:
                ang = math.atan2(aim.y, aim.x)
                speed = 560
                spread = 0.0
                bullets_to_fire = 1
                if self.player.spread_timer > 0:
                    bullets_to_fire = 5
                    spread = 0.18
                for i in range(bullets_to_fire):
                    offs = (i - (bullets_to_fire - 1) / 2) * spread
                    dir = pygame.Vector2(math.cos(ang + offs), math.sin(ang + offs))
                    vel = dir * speed
                    self.bullets.append(Bullet(self.player.pos + dir * (self.player.radius + 6), vel, dmg=1))
                self.player.reset_cooldown()
                self.add_muzzle(self.player.pos + pygame.Vector2(math.cos(ang), math.sin(ang)) * (self.player.radius + 6), ang)

        # Enemy spawning (gentler early game)
        self.spawn_timer -= dt
        spawn_interval = self.spawn_rate_for(self.level)
        if self.spawn_timer <= 0:
            swarm = random.random() < min(0.03 + self.level * 0.008, 0.14)
            count = 1 if not swarm else random.randint(3, 5)
            for _ in range(count):
                self.spawn_enemy()
            self.spawn_timer = spawn_interval

        # Update enemies
        for e in self.enemies:
            e.update(dt, self.player.pos, self.barriers)

        # Update bullets
        for b in self.bullets:
            b.update(dt)

        # Collisions: bullets vs enemies
        for b in list(self.bullets):
            if not b.alive:
                continue
            for e in list(self.enemies):
                if not e.alive:
                    continue
                if (e.pos - b.pos).length() <= e.radius + b.radius:
                    e.hit(b.dmg)
                    if b.pierce <= 0:
                        b.alive = False
                    else:
                        b.pierce -= 1
                    self.particles.append(Particle(b.pos, (0, 0), 0.12, 3, YELLOW))
                    self.camera.shake(1.2)
                    if not e.alive:
                        self.on_enemy_killed(e)
                    break

        # Enemy touching player
        for e in list(self.enemies):
            if not e.alive:
                continue
            if (e.pos - self.player.pos).length() <= e.radius + self.player.radius:
                if self.player.damage(e.damage):
                    self.camera.shake(7)
                    self.flash = 0.35
                e.alive = False
                self.add_explosion(e.pos, e.color)

        

        # Cleanup
        self.enemies = [e for e in self.enemies if e.alive]
        self.bullets = [b for b in self.bullets if b.alive]
        self.particles = [pt for pt in self.particles if pt.update(dt)]

        # Flash decay
        self.flash = max(0.0, self.flash - dt)

        # Death
        if self.player.hp <= 0:
            self.state = "gameover"

    def on_enemy_killed(self, e: Enemy):
        self.player.add_score(10 if e.kind != "tank" else 20)
        self.add_explosion(e.pos, e.color)
        for _ in range(8):
            vel = (random.uniform(-30, 30), random.uniform(-80, -20))
            self.particles.append(Particle(e.pos, vel, 0.6, 2, WHITE))

   
    # ---------- Draw ----------
    def draw_grid_background(self):
        self.surface.fill(BLACK)
        g = 36
        ox = (math.sin(self.bg_t * 0.6) * 30)
        oy = (math.cos(self.bg_t * 0.4) * 30)
        for x in range(-g, VIRTUAL_W + g, g):
            pygame.draw.line(self.surface, (20, 22, 30), (x + ox, 0), (x + ox, VIRTUAL_H))
        for y in range(-g, VIRTUAL_H + g, g):
            pygame.draw.line(self.surface, (20, 22, 30), (0, y + oy), (VIRTUAL_W, y + oy))

    def draw_ui(self):
        font = pygame.font.SysFont("consolas", 20)
        big = pygame.font.SysFont("consolas", 40, bold=True)

        # HP bar
        hp_pct = self.player.hp / self.player.max_hp
        pygame.draw.rect(self.surface, (40, 40, 50), (20, 14, 220, 20), border_radius=8)
        pygame.draw.rect(self.surface, RED if hp_pct < 0.35 else GREEN, (20, 14, int(220 * hp_pct), 20), border_radius=8)
        self.surface.blit(font.render(f"HP {self.player.hp:3d}", True, WHITE), (24, 16))

        # Score & Level
        self.surface.blit(font.render(f"Score {self.player.score}", True, WHITE), (VIRTUAL_W - 160, 14))
        self.surface.blit(font.render(f"Best {self.player.high_score}", True, GRAY), (VIRTUAL_W - 160, 36))
        self.surface.blit(font.render(f"Level {self.level}", True, WHITE), (VIRTUAL_W - 160, 58))

        # Survival goal timer
        goal = self.goal_time_for(self.level)
        left = self.level_time_left
        pct = 1.0 - (left / goal)
        bar_w = 260
        x = VIRTUAL_W // 2 - bar_w // 2
        y = 14
        pygame.draw.rect(self.surface, (40, 40, 50), (x, y, bar_w, 20), border_radius=8)
        pygame.draw.rect(self.surface, YELLOW, (x, y, int(bar_w * pct), 20), border_radius=8)
        self.surface.blit(font.render(f"Survive: {left:0.1f}s", True, WHITE), (x + 6, y + 1))

        # Combo meter
        combo = self.player.combo
        if combo > 1.0:
            self.surface.blit(big.render(f"x{combo:.1f}", True, YELLOW), (VIRTUAL_W/2 - 28, 40))

      

    def draw_scene(self, paused: bool = False):
        self.draw_grid_background()

        # Particles behind entities
        for p in self.particles:
            p.draw(self.surface, self.camera)

        # Barriers
        for b in self.barriers:
            b.draw(self.surface, self.camera)

        # Entities
        mouse_world = self.world_mouse()
        self.player.draw(self.surface, self.camera, mouse_world)
        for b in self.bullets:
            b.draw(self.surface, self.camera)
        for e in self.enemies:
            e.draw(self.surface, self.camera)
        

        # Damage flash overlay
        if self.flash > 0:
            a = int(150 * self.flash)
            overlay = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
            overlay.fill((255, 50, 50, a))
            self.surface.blit(overlay, (0, 0))

        self.draw_ui()

        if paused:
            self.draw_center_text("PAUSED — Press ESC to resume")

    def draw_center_text(self, text):
        big = pygame.font.SysFont("consolas", 36, bold=True)
        small = pygame.font.SysFont("consolas", 20)
        s1 = big.render(text, True, WHITE)
        s2 = small.render("ARROWS: move • Mouse: aim • LMB: shoot", True, GRAY)
        self.surface.blit(s1, (VIRTUAL_W/2 - s1.get_width()/2, VIRTUAL_H/2 - 30))
        self.surface.blit(s2, (VIRTUAL_W/2 - s2.get_width()/2, VIRTUAL_H/2 + 12))

    def draw_menu(self):
        self.draw_grid_background()
        title = pygame.font.SysFont("consolas", 46, bold=True).render("Top‑Down Shooter", True, WHITE)
        self.surface.blit(title, (VIRTUAL_W/2 - title.get_width()/2, VIRTUAL_H/2 - 120))
        self.draw_center_text("Press ENTER or Click to Start")

    def draw_cleared(self):
        # darken screen
        overlay = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.surface.blit(overlay, (0, 0))
        big = pygame.font.SysFont("consolas", 40, bold=True)
        small = pygame.font.SysFont("consolas", 22)
        s1 = big.render(f"LEVEL {self.level} CLEARED!", True, GREEN)
        s2 = small.render("Press N for Next Level  •  R to Retry  ", True, WHITE)
        self.surface.blit(s1, (VIRTUAL_W/2 - s1.get_width()/2, VIRTUAL_H/2 - 40))
        self.surface.blit(s2, (VIRTUAL_W/2 - s2.get_width()/2, VIRTUAL_H/2 + 6))

    def draw_gameover(self):
        self.draw_scene()
        self.draw_center_text("GAME OVER — Press ENTER to Restart")

    # ---------- Present ----------
    def blit_to_window(self):
        win_w, win_h = self.window.get_size()
        scale = min(win_w / VIRTUAL_W, win_h / VIRTUAL_H)
        surf_w, surf_h = int(VIRTUAL_W * scale), int(VIRTUAL_H * scale)
        x_off = (win_w - surf_w) // 2
        y_off = (win_h - surf_h) // 2

        if self.player.shield > 0:
            self.player.shield = max(0.0, self.player.shield - self.clock.get_time() / 1000.0 * 0.25)

        scaled = pygame.transform.smoothscale(self.surface, (surf_w, surf_h))
        self.window.fill((5, 6, 10))
        self.window.blit(scaled, (x_off, y_off))
        pygame.display.flip()


if __name__ == "__main__":
    Game().run()
