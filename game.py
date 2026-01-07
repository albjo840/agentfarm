import pygame

class HorseGame:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((800, 600))
        self.clock = pygame.time.Clock()
        self.horse = pygame.Rect(100, 100, 50, 50)
        self.player = pygame.Rect(400, 300, 50, 50)

    def run(self):
        running = True
        while running:
            for event in pygame.event.get):
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_UP:
                        self.player.move_ip(0, -5)
                    if event.key == pygame.K_DOWN:
                        self.player.move_ip(0, 5)
                    if event.key == pygame.K_LEFT:
                        self.player.move_ip(-5, 0)
                    if event.key == pygame.K_RIGHT:
                        self.player.move_ip(5, 0)

            self.screen.fill((0, 0, 0))
            pygame.draw.rect(self.screen, (255, 255, 255), self.horse)
            pygame.draw.rect(self.screen, (255, 0, 0), self.player)
            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()

game = HorseGame()
-game.run()