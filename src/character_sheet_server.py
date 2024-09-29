from livereload import Server

character_sheet_html_file = "character_sheet.html"

def start_character_sheet_server(delay):
    server = Server()
    server.watch(character_sheet_html_file)  # Watch the HTML file for changes
    server.serve(
        root='.',
        port=5500,
        open_url_delay=delay,
        default_filename=character_sheet_html_file
    )

if __name__ == "__main__":
    start_character_sheet_server(0.5)