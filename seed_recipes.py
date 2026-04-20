from app import app, db
from models import ManufacturingRecipe

def seed():
    with app.app_context():
        # Check if already seeded
        if ManufacturingRecipe.query.first():
            print("Recipes already exist.")
            return

        recipes = [
            {
                "name": "Ivory White",
                "category": "Color",
                "color_hex": "#FFFFF0",
                "composition": {
                    "Soy Wax": "1000g",
                    "Dye (Ivory)": "2g",
                    "Fragrance Oil": "80ml"
                },
                "instructions": "Mix dye at 80°C. Add fragrance at 70°C. Pour at 62°C for smooth finish."
            },
            {
                "name": "Midnight Lavender",
                "category": "Full Recipe",
                "color_hex": "#4B0082",
                "composition": {
                    "Hard Soy Wax": "800g",
                    "Soft Soy Wax": "200g",
                    "Dye (Navy)": "4g",
                    "Dye (Violet)": "1g",
                    "Lavender Oil": "90ml"
                },
                "instructions": "Double dye for deep opacity. Cure for 14 days for optimal scent throw."
            },
            {
                "name": "Sage Green",
                "category": "Color",
                "color_hex": "#8A9A5B",
                "composition": {
                    "Soy Wax": "1000g",
                    "Dye (Green)": "3g",
                    "Dye (Brown)": "0.5g",
                    "Fragrance (Fresh Linen)": "70ml"
                },
                "instructions": "Mix Green and Brown dyes together before adding to wax for earthy tone."
            }
        ]

        for r in recipes:
            new_r = ManufacturingRecipe(
                name=r['name'],
                category=r['category'],
                color_hex=r['color_hex'],
                composition=r['composition'],
                instructions=r['instructions']
            )
            db.session.add(new_r)
        
        db.session.commit()
        print("Seeded 3 manufacturing recipes successfully.")

if __name__ == "__main__":
    seed()
