def load_image(file_name, size=None):
    import os
    import pygame

    path = os.path.join('assets', file_name)
    try:
        image = pygame.image.load(path).convert_alpha()
        if size:
            return pygame.transform.scale(image, size)
        return image
    except pygame.error as e:
        print(f"Cannot load image: {path}. Error: {e}")
        print(f"Please ensure you have created the 'assets' folder and the file '{file_name}'!")
        placeholder_size = size if size else (100, 100)
        placeholder = pygame.Surface(placeholder_size)
        placeholder.fill((0, 150, 0))
        return placeholder

def get_game_settings():
    return {
        "screen_width": 800,
        "screen_height": 600,
        "fps": 60,
        "game_time": 30
    }