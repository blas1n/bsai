"""BSAI CLI Entry Point"""
import typer
from rich.console import Console

app = typer.Typer(name="bsai", help="BS AI Agent for Development")
console = Console()

@app.command()
def hello(name: str = "Developer"):
    """Say hello to get started with BSAI"""
    console.print(f"Hello {name}! BSAI is ready to help!", style="bold green")
    console.print("Available commands will be added as we develop...")

@app.command()
def status():
    """Check BSAI system status"""
    console.print("BSAI Core: Ready", style="green")
    console.print("Development Mode: Active", style="yellow")
    console.print("Documentation: http://localhost:8001", style="blue")

if __name__ == "__main__":
    app()