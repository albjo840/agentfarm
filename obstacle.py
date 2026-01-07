class Obstacle:
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.velocity = 2

    def update(self):
        self.x -= self.velocity
        if self.x < 0:
            self.x = 800

    def render(self):
        # render obstacle
        pass
