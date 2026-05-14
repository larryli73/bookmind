"""
Ingest high-quality children's books from curated award/classic lists.
- Google Books API for metadata (cover, description, page count, ISBN)
- Claude Haiku for learning goal classification
- Skips books already in DB; enriches metadata if missing

Run: DATABASE_URL="postgresql://..." ANTHROPIC_API_KEY="sk-..." python scripts/ingest_award_books.py
"""
import asyncio
import asyncpg
import httpx
import json
import os
import re
import time

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:eRrNwgeutWVANDhVskIKbCkOJXQhRIWn@viaduct.proxy.rlwy.net:33806/railway"
).replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_BOOKS_KEY = os.getenv("GOOGLE_BOOKS_API_KEY", "")

VALID_GOALS = [
    "kindness", "courage", "friendship", "emotions", "science",
    "history", "diversity", "resilience", "problem_solving",
    "environment", "family", "creativity"
]

# ── Curated Book List ─────────────────────────────────────────────────────────
# Format: (title, author, age_min, age_max, [goals], [awards])
# Goals are pre-seeded; Claude will validate/extend from the description.

CURATED_BOOKS = [
    # ── Newbery Medal Winners ──────────────────────────────────────────────────
    ("The Giver", "Lois Lowry", 10, 14, ["courage", "history", "problem_solving"], ["Newbery Medal 1994"]),
    ("Holes", "Louis Sachar", 9, 12, ["friendship", "resilience", "history"], ["Newbery Medal 1999"]),
    ("Bud, Not Buddy", "Christopher Paul Curtis", 9, 12, ["resilience", "family", "history"], ["Newbery Medal 2000"]),
    ("A Single Shard", "Linda Sue Park", 9, 12, ["resilience", "creativity", "history"], ["Newbery Medal 2002"]),
    ("The Tale of Despereaux", "Kate DiCamillo", 7, 11, ["courage", "kindness", "friendship"], ["Newbery Medal 2004"]),
    ("Kira-Kira", "Cynthia Kadohata", 9, 12, ["family", "resilience", "history"], ["Newbery Medal 2005"]),
    ("The Graveyard Book", "Neil Gaiman", 10, 14, ["courage", "family", "friendship"], ["Newbery Medal 2009"]),
    ("When You Reach Me", "Rebecca Stead", 9, 12, ["friendship", "problem_solving", "courage"], ["Newbery Medal 2010"]),
    ("Moon Over Manifest", "Clare Vanderpool", 9, 12, ["history", "resilience", "friendship"], ["Newbery Medal 2011"]),
    ("The One and Only Ivan", "Katherine Applegate", 8, 12, ["courage", "friendship", "environment"], ["Newbery Medal 2013"]),
    ("Flora & Ulysses", "Kate DiCamillo", 8, 12, ["creativity", "family", "kindness"], ["Newbery Medal 2014"]),
    ("The Crossover", "Kwame Alexander", 9, 12, ["family", "resilience", "emotions"], ["Newbery Medal 2015"]),
    ("Last Stop on Market Street", "Matt de la Peña", 4, 8, ["kindness", "diversity", "family"], ["Newbery Medal 2016"]),
    ("Hello, Universe", "Erin Entrada Kelly", 8, 12, ["friendship", "courage", "diversity"], ["Newbery Medal 2018"]),
    ("Merci Suarez Changes Gears", "Meg Medina", 9, 12, ["family", "resilience", "diversity"], ["Newbery Medal 2019"]),
    ("New Kid", "Jerry Craft", 8, 12, ["diversity", "friendship", "courage"], ["Newbery Medal 2020"]),
    ("When You Trap a Tiger", "Tae Keller", 8, 12, ["family", "courage", "creativity"], ["Newbery Medal 2021"]),
    ("The Last Cuentista", "Donna Barba Higuera", 9, 12, ["courage", "family", "creativity"], ["Newbery Medal 2022"]),
    ("Freewater", "Amina Luqman-Dawson", 9, 12, ["history", "courage", "resilience"], ["Newbery Medal 2023"]),
    ("The Eyes and the Impossible", "Dave Eggers", 8, 12, ["friendship", "courage", "environment"], ["Newbery Medal 2024"]),

    # ── Newbery Honor / Notable ────────────────────────────────────────────────
    ("Number the Stars", "Lois Lowry", 9, 12, ["courage", "history", "friendship"], ["Newbery Medal 1990"]),
    ("Maniac Magee", "Jerry Spinelli", 9, 12, ["diversity", "resilience", "kindness"], ["Newbery Medal 1991"]),
    ("Shiloh", "Phyllis Reynolds Naylor", 8, 12, ["courage", "kindness", "family"], ["Newbery Medal 1992"]),
    ("Missing May", "Cynthia Rylant", 9, 12, ["family", "resilience", "emotions"], ["Newbery Medal 1993"]),
    ("Walk Two Moons", "Sharon Creech", 9, 12, ["family", "resilience", "emotions"], ["Newbery Medal 1995"]),
    ("The Midwife's Apprentice", "Karen Cushman", 9, 12, ["resilience", "history", "courage"], ["Newbery Medal 1996"]),
    ("The View from Saturday", "E.L. Konigsburg", 9, 12, ["friendship", "problem_solving", "kindness"], ["Newbery Medal 1997"]),
    ("Out of the Dust", "Karen Hesse", 9, 12, ["resilience", "history", "family"], ["Newbery Medal 1998"]),
    ("Esperanza Rising", "Pam Muñoz Ryan", 8, 12, ["resilience", "family", "history"], ["Pura Belpré Award"]),
    ("Island of the Blue Dolphins", "Scott O'Dell", 9, 12, ["resilience", "courage", "environment"], ["Newbery Medal 1961"]),
    ("It's Like This, Cat", "Emily Cheney Neville", 9, 12, ["family", "emotions", "friendship"], ["Newbery Medal 1964"]),
    ("Shadow of a Bull", "Maia Wojciechowska", 9, 12, ["courage", "resilience", "history"], ["Newbery Medal 1965"]),
    ("From the Mixed-Up Files of Mrs. Basil E. Frankweiler", "E.L. Konigsburg", 9, 12, ["problem_solving", "courage", "creativity"], ["Newbery Medal 1968"]),
    ("Sounder", "William H. Armstrong", 9, 13, ["resilience", "family", "history"], ["Newbery Medal 1970"]),
    ("Mrs. Frisby and the Rats of NIMH", "Robert C. O'Brien", 9, 12, ["courage", "science", "problem_solving"], ["Newbery Medal 1972"]),
    ("Julie of the Wolves", "Jean Craighead George", 9, 13, ["resilience", "environment", "courage"], ["Newbery Medal 1973"]),
    ("The Slave Dancer", "Paula Fox", 10, 14, ["history", "courage", "resilience"], ["Newbery Medal 1974"]),
    ("M.C. Higgins, the Great", "Virginia Hamilton", 9, 12, ["family", "environment", "resilience"], ["Newbery Medal 1975"]),
    ("The Grey King", "Susan Cooper", 9, 12, ["courage", "problem_solving", "family"], ["Newbery Medal 1976"]),
    ("Roll of Thunder, Hear My Cry", "Mildred D. Taylor", 9, 13, ["history", "courage", "family"], ["Newbery Medal 1977"]),
    ("Bridge to Terabithia", "Katherine Paterson", 9, 12, ["friendship", "emotions", "resilience"], ["Newbery Medal 1978"]),
    ("The Westing Game", "Ellen Raskin", 9, 13, ["problem_solving", "friendship", "diversity"], ["Newbery Medal 1979"]),
    ("A Gathering of Days", "Joan W. Blos", 9, 12, ["history", "family", "courage"], ["Newbery Medal 1980"]),
    ("Jacob Have I Loved", "Katherine Paterson", 9, 13, ["family", "resilience", "emotions"], ["Newbery Medal 1981"]),
    ("A Visit to William Blake's Inn", "Nancy Willard", 6, 10, ["creativity", "courage", "family"], ["Newbery Medal 1982"]),
    ("Dicey's Song", "Cynthia Voigt", 9, 13, ["family", "resilience", "courage"], ["Newbery Medal 1983"]),
    ("Dear Mr. Henshaw", "Beverly Cleary", 8, 12, ["emotions", "family", "resilience"], ["Newbery Medal 1984"]),
    ("The Hero and the Crown", "Robin McKinley", 10, 14, ["courage", "history", "problem_solving"], ["Newbery Medal 1985"]),
    ("Sarah, Plain and Tall", "Patricia MacLachlan", 7, 11, ["family", "resilience", "kindness"], ["Newbery Medal 1986"]),
    ("The Whipping Boy", "Sid Fleischman", 8, 12, ["friendship", "courage", "resilience"], ["Newbery Medal 1987"]),
    ("Lincoln: A Photobiography", "Russell Freedman", 9, 13, ["history", "courage", "resilience"], ["Newbery Medal 1988"]),
    ("Joyful Noise: Poems for Two Voices", "Paul Fleischman", 8, 12, ["creativity", "environment", "science"], ["Newbery Medal 1989"]),
    ("Maniac Magee", "Jerry Spinelli", 9, 12, ["diversity", "resilience", "kindness"], ["Newbery Medal 1991"]),
    ("Hatchet", "Gary Paulsen", 9, 12, ["resilience", "courage", "environment"], ["Newbery Honor 1988"]),
    ("Tuck Everlasting", "Natalie Babbitt", 9, 12, ["family", "courage", "history"], []),
    ("A Long Walk to Water", "Linda Sue Park", 9, 13, ["resilience", "courage", "history"], []),

    # ── Caldecott Medal & Honor (Picture Books) ───────────────────────────────
    ("Where the Wild Things Are", "Maurice Sendak", 3, 8, ["emotions", "creativity", "family"], ["Caldecott Medal 1964"]),
    ("The Snowy Day", "Ezra Jack Keats", 3, 6, ["diversity", "creativity", "family"], ["Caldecott Medal 1963"]),
    ("Jumanji", "Chris Van Allsburg", 5, 9, ["courage", "problem_solving", "creativity"], ["Caldecott Medal 1982"]),
    ("The Polar Express", "Chris Van Allsburg", 4, 8, ["courage", "creativity", "family"], ["Caldecott Medal 1986"]),
    ("Owl Moon", "Jane Yolen", 3, 7, ["family", "environment", "creativity"], ["Caldecott Medal 1988"]),
    ("Tuesday", "David Wiesner", 3, 7, ["creativity", "problem_solving"], ["Caldecott Medal 1992"]),
    ("Smoky Night", "Eve Bunting", 5, 9, ["diversity", "kindness", "family"], ["Caldecott Medal 1995"]),
    ("Officer Buckle and Gloria", "Peggy Rathmann", 4, 8, ["friendship", "problem_solving", "kindness"], ["Caldecott Medal 1996"]),
    ("Snowflake Bentley", "Jacqueline Briggs Martin", 5, 9, ["science", "resilience", "creativity"], ["Caldecott Medal 1999"]),
    ("Joseph Had a Little Overcoat", "Simms Taback", 3, 7, ["creativity", "resilience", "family"], ["Caldecott Medal 2000"]),
    ("So You Want to Be President?", "Judith St. George", 6, 10, ["history", "courage", "creativity"], ["Caldecott Medal 2001"]),
    ("The Three Pigs", "David Wiesner", 4, 8, ["creativity", "problem_solving", "courage"], ["Caldecott Medal 2002"]),
    ("The Man Who Walked Between the Towers", "Mordicai Gerstein", 5, 9, ["courage", "creativity", "resilience"], ["Caldecott Medal 2004"]),
    ("Kitten's First Full Moon", "Kevin Henkes", 2, 5, ["emotions", "family", "resilience"], ["Caldecott Medal 2005"]),
    ("Flotsam", "David Wiesner", 4, 8, ["creativity", "science", "environment"], ["Caldecott Medal 2007"]),
    ("The House in the Night", "Susan Marie Swanson", 2, 5, ["family", "creativity", "emotions"], ["Caldecott Medal 2009"]),
    ("The Lion & the Mouse", "Jerry Pinkney", 3, 7, ["kindness", "friendship", "courage"], ["Caldecott Medal 2010"]),
    ("A Ball for Daisy", "Chris Raschka", 2, 5, ["emotions", "friendship", "resilience"], ["Caldecott Medal 2012"]),
    ("This Is Not My Hat", "Jon Klassen", 3, 7, ["courage", "problem_solving"], ["Caldecott Medal 2013"]),
    ("Locomotive", "Brian Floca", 6, 10, ["history", "science", "creativity"], ["Caldecott Medal 2014"]),
    ("The Adventures of Beekle: The Unimaginary Friend", "Dan Santat", 4, 8, ["creativity", "courage", "friendship"], ["Caldecott Medal 2015"]),
    ("Finding Winnie: The True Story of the World's Most Famous Bear", "Lindsay Mattick", 4, 8, ["family", "courage", "history"], ["Caldecott Medal 2016"]),
    ("Radiant Child: The Story of Young Artist Jean-Michel Basquiat", "Javaka Steptoe", 5, 9, ["creativity", "diversity", "resilience"], ["Caldecott Medal 2017"]),
    ("Wolf in the Snow", "Matthew Cordell", 4, 8, ["kindness", "courage", "environment"], ["Caldecott Medal 2018"]),
    ("Hello Lighthouse", "Sophie Blackall", 4, 8, ["family", "resilience", "history"], ["Caldecott Medal 2019"]),
    ("The Undefeated", "Kwame Alexander", 5, 10, ["history", "resilience", "diversity"], ["Caldecott Medal 2020"]),
    ("We Are Water Protectors", "Carole Lindstrom", 4, 8, ["environment", "courage", "diversity"], ["Caldecott Medal 2021"]),
    ("Watercress", "Andrea Wang", 4, 8, ["family", "diversity", "resilience"], ["Caldecott Medal 2022"]),
    ("Fry Bread: A Native American Family Story", "Kevin Noble Maillard", 4, 8, ["family", "diversity", "history"], ["Caldecott Honor 2020"]),
    ("When Stars Are Scattered", "Victoria Jamieson", 8, 12, ["resilience", "history", "family"], ["Schneider Family Book Award"]),
    ("Eyes That Kiss in the Corners", "Joanna Ho", 3, 7, ["diversity", "family", "kindness"], []),

    # ── Classic Children's Literature ─────────────────────────────────────────
    ("Charlotte's Web", "E.B. White", 7, 11, ["friendship", "kindness", "family"], []),
    ("Stuart Little", "E.B. White", 6, 10, ["courage", "family", "creativity"], []),
    ("The Trumpet of the Swan", "E.B. White", 7, 11, ["courage", "creativity", "resilience"], []),
    ("Harriet the Spy", "Louise Fitzhugh", 8, 12, ["courage", "friendship", "emotions"], []),
    ("A Cricket in Times Square", "George Selden", 7, 11, ["friendship", "creativity", "family"], []),
    ("The Wind in the Willows", "Kenneth Grahame", 7, 11, ["friendship", "family", "environment"], []),
    ("The Secret Garden", "Frances Hodgson Burnett", 8, 12, ["resilience", "family", "environment"], []),
    ("Mary Poppins", "P.L. Travers", 6, 10, ["creativity", "family", "courage"], []),
    ("Pippi Longstocking", "Astrid Lindgren", 6, 10, ["courage", "creativity", "friendship"], []),
    ("The Little Prince", "Antoine de Saint-Exupéry", 8, 12, ["friendship", "emotions", "creativity"], []),
    ("Alice's Adventures in Wonderland", "Lewis Carroll", 7, 12, ["creativity", "courage", "problem_solving"], []),
    ("The Wizard of Oz", "L. Frank Baum", 6, 10, ["courage", "friendship", "family"], []),
    ("Peter Pan", "J.M. Barrie", 6, 10, ["creativity", "courage", "family"], []),
    ("Treasure Island", "Robert Louis Stevenson", 9, 14, ["courage", "problem_solving", "history"], []),
    ("Robin Hood", "Howard Pyle", 9, 14, ["courage", "history", "resilience"], []),
    ("The Count of Monte Cristo (abridged)", "Alexandre Dumas", 10, 14, ["resilience", "courage", "history"], []),
    ("Swiss Family Robinson", "Johann David Wyss", 8, 13, ["family", "courage", "environment"], []),
    ("Robinson Crusoe", "Daniel Defoe", 10, 14, ["resilience", "courage", "environment"], []),
    ("The Phantom Tollbooth", "Norton Juster", 8, 12, ["creativity", "problem_solving", "courage"], []),
    ("A Wrinkle in Time", "Madeleine L'Engle", 9, 13, ["science", "courage", "family"], ["Newbery Medal 1963"]),
    ("James and the Giant Peach", "Roald Dahl", 7, 11, ["creativity", "courage", "resilience"], []),
    ("Charlie and the Chocolate Factory", "Roald Dahl", 7, 11, ["creativity", "courage", "kindness"], []),
    ("Matilda", "Roald Dahl", 7, 11, ["courage", "resilience", "creativity"], []),
    ("The BFG", "Roald Dahl", 6, 10, ["courage", "friendship", "creativity"], []),
    ("Danny the Champion of the World", "Roald Dahl", 7, 11, ["family", "courage", "resilience"], []),
    ("Fantastic Mr Fox", "Roald Dahl", 5, 9, ["family", "problem_solving", "courage"], []),
    ("The Witches", "Roald Dahl", 7, 11, ["courage", "family", "problem_solving"], []),
    ("George's Marvellous Medicine", "Roald Dahl", 5, 9, ["creativity", "family", "problem_solving"], []),

    # ── Popular Series (Book 1) ────────────────────────────────────────────────
    ("Percy Jackson and the Lightning Thief", "Rick Riordan", 9, 12, ["courage", "friendship", "problem_solving"], []),
    ("Diary of a Wimpy Kid", "Jeff Kinney", 8, 12, ["friendship", "problem_solving", "emotions"], []),
    ("Dog Man", "Dav Pilkey", 6, 10, ["courage", "friendship", "problem_solving"], []),
    ("Big Nate: In a Class by Himself", "Lincoln Peirce", 8, 12, ["friendship", "resilience", "problem_solving"], []),
    ("Captain Underpants and the Perilous Plot of Professor Poopypants", "Dav Pilkey", 6, 10, ["courage", "friendship", "problem_solving"], []),
    ("Magic Tree House: Dinosaurs Before Dark", "Mary Pope Osborne", 6, 9, ["science", "history", "courage"], []),
    ("Junie B. Jones and the Stupid Smelly Bus", "Barbara Park", 5, 8, ["emotions", "courage", "friendship"], []),
    ("Cam Jansen and the Mystery of the Stolen Diamonds", "David A. Adler", 6, 9, ["problem_solving", "friendship", "courage"], []),
    ("Nate the Great", "Marjorie Weinman Sharmat", 5, 8, ["problem_solving", "friendship", "courage"], []),
    ("Encyclopedia Brown, Boy Detective", "Donald J. Sobol", 7, 11, ["problem_solving", "courage", "friendship"], []),
    ("The Boxcar Children", "Gertrude Chandler Warner", 6, 10, ["family", "problem_solving", "resilience"], []),
    ("Geronimo Stilton: Lost Treasure of the Emerald Eye", "Geronimo Stilton", 6, 9, ["friendship", "courage", "problem_solving"], []),
    ("Ivy and Bean", "Annie Barrows", 5, 8, ["friendship", "kindness", "problem_solving"], []),
    ("Clementine", "Sara Pennypacker", 7, 10, ["friendship", "emotions", "family"], []),
    ("Ramona the Pest", "Beverly Cleary", 6, 10, ["emotions", "family", "courage"], []),
    ("Henry Huggins", "Beverly Cleary", 7, 11, ["family", "friendship", "problem_solving"], []),
    ("The Penderwicks", "Jeanne Birdsall", 8, 12, ["family", "friendship", "resilience"], ["National Book Award"]),
    ("The Mysterious Benedict Society", "Trenton Lee Stewart", 9, 13, ["problem_solving", "friendship", "courage"], []),
    ("The Invention of Hugo Cabret", "Brian Selznick", 9, 12, ["creativity", "history", "resilience"], ["Caldecott Medal 2008"]),

    # ── Picture Books & Early Readers ────────────────────────────────────────────
    ("Goodnight Moon", "Margaret Wise Brown", 1, 5, ["family", "emotions"], []),
    ("The Very Hungry Caterpillar", "Eric Carle", 2, 5, ["science", "creativity"], []),
    ("Guess How Much I Love You", "Sam McBratney", 2, 5, ["family", "emotions", "kindness"], []),
    ("The Very Lonely Firefly", "Eric Carle", 2, 5, ["friendship", "emotions"], []),
    ("Chrysanthemum", "Kevin Henkes", 4, 8, ["kindness", "emotions", "friendship"], []),
    ("Chester's Way", "Kevin Henkes", 4, 8, ["friendship", "diversity", "kindness"], []),
    ("Lilly's Purple Plastic Purse", "Kevin Henkes", 4, 8, ["emotions", "family", "friendship"], []),
    ("Owen", "Kevin Henkes", 3, 6, ["family", "emotions", "resilience"], []),
    ("Wemberly Worried", "Kevin Henkes", 3, 7, ["emotions", "courage", "friendship"], []),
    ("Julius, the Baby of the World", "Kevin Henkes", 3, 7, ["family", "emotions", "kindness"], []),
    ("Amos & Boris", "William Steig", 4, 8, ["friendship", "kindness", "courage"], []),
    ("Sylvester and the Magic Pebble", "William Steig", 4, 8, ["family", "problem_solving", "emotions"], []),
    ("Doctor De Soto", "William Steig", 4, 8, ["problem_solving", "courage", "kindness"], []),
    ("The Courage of Sarah Noble", "Alice Dalgliesh", 6, 10, ["courage", "history", "family"], ["Newbery Honor 1955"]),
    ("Frog and Toad Are Friends", "Arnold Lobel", 5, 8, ["friendship", "kindness", "emotions"], ["Caldecott Honor 1971"]),
    ("Frog and Toad Together", "Arnold Lobel", 5, 8, ["friendship", "courage", "kindness"], ["Newbery Honor 1973"]),
    ("Corduroy", "Don Freeman", 2, 6, ["friendship", "family", "emotions"], []),
    ("The Berenstain Bears and the Trouble with Friends", "Stan Berenstain", 3, 7, ["friendship", "kindness", "emotions"], []),
    ("If You Give a Mouse a Cookie", "Laura Numeroff", 3, 6, ["creativity", "family", "problem_solving"], []),
    ("The Stinky Cheese Man and Other Fairly Stupid Tales", "Jon Scieszka", 5, 9, ["creativity", "problem_solving"], []),
    ("Knuffle Bunny: A Cautionary Tale", "Mo Willems", 2, 6, ["family", "emotions", "resilience"], ["Caldecott Honor 2005"]),
    ("Don't Let the Pigeon Drive the Bus!", "Mo Willems", 2, 6, ["problem_solving", "emotions"], ["Caldecott Honor 2004"]),
    ("Elephant and Piggie: We Are in a Book!", "Mo Willems", 4, 8, ["friendship", "emotions", "creativity"], []),
    ("Scaredy Squirrel", "Mélanie Watt", 4, 8, ["courage", "emotions", "problem_solving"], []),
    ("Diary of a Worm", "Doreen Cronin", 4, 8, ["creativity", "science", "family"], []),
    ("Click, Clack, Moo: Cows That Type", "Doreen Cronin", 4, 8, ["problem_solving", "creativity", "kindness"], ["Caldecott Honor 2001"]),
    ("Stellaluna", "Janell Cannon", 4, 8, ["diversity", "family", "friendship"], []),
    ("Anansi the Spider: A Tale from the Ashanti", "Gerald McDermott", 4, 8, ["creativity", "problem_solving", "family"], ["Caldecott Honor 1973"]),
    ("Lon Po Po: A Red-Riding Hood Story from China", "Ed Young", 4, 8, ["courage", "family", "problem_solving"], ["Caldecott Medal 1990"]),
    ("Mufaro's Beautiful Daughters", "John Steptoe", 4, 8, ["kindness", "diversity", "resilience"], ["Caldecott Honor 1988"]),
    ("Amazing Grace", "Mary Hoffman", 5, 8, ["courage", "resilience", "diversity"], []),
    ("The Name Jar", "Yangsook Choi", 5, 9, ["diversity", "courage", "friendship"], []),
    ("Each Kindness", "Jacqueline Woodson", 5, 9, ["kindness", "emotions", "friendship"], []),
    ("Each Little Bird That Sings", "Deborah Wiles", 8, 12, ["family", "resilience", "emotions"], ["Newbery Honor 2006"]),
    ("Enemy Pie", "Derek Munson", 4, 8, ["kindness", "friendship", "problem_solving"], []),
    ("Enemy Pie", "Derek Munson", 4, 8, ["kindness", "friendship"], []),
    ("The Recess Queen", "Alexis O'Neill", 4, 8, ["kindness", "courage", "friendship"], []),
    ("Stand in My Shoes", "Bob Sornson", 4, 8, ["kindness", "diversity", "emotions"], []),
    ("Those Shoes", "Maribeth Boelts", 4, 8, ["kindness", "family", "resilience"], []),
    ("One", "Kathryn Otoshi", 3, 7, ["courage", "kindness", "diversity"], []),
    ("Zero", "Kathryn Otoshi", 3, 7, ["resilience", "kindness", "courage"], []),
    ("Beautiful Oops!", "Barney Saltzberg", 3, 7, ["creativity", "resilience", "emotions"], []),
    ("Ish", "Peter H. Reynolds", 4, 8, ["creativity", "resilience", "emotions"], []),
    ("The Dot", "Peter H. Reynolds", 4, 8, ["creativity", "resilience", "courage"], []),
    ("Sky Color", "Peter H. Reynolds", 4, 8, ["creativity", "problem_solving"], []),
    ("Rosie Revere, Engineer", "Andrea Beaty", 4, 8, ["science", "resilience", "creativity"], []),
    ("Iggy Peck, Architect", "Andrea Beaty", 4, 8, ["science", "creativity", "courage"], []),
    ("Ada Twist, Scientist", "Andrea Beaty", 4, 8, ["science", "curiosity", "creativity"], []),
    ("The Questioneers Picture Book Collection", "Andrea Beaty", 4, 8, ["science", "creativity", "problem_solving"], []),
    ("Counting by 7s", "Holly Goldberg Sloan", 9, 12, ["resilience", "friendship", "science"], []),
    ("The Wild Robot", "Peter Brown", 8, 12, ["science", "resilience", "family"], []),
    ("The Wild Robot Escapes", "Peter Brown", 8, 12, ["family", "resilience", "science"], []),

    # ── STEM & Science ────────────────────────────────────────────────────────
    ("Hidden Figures Young Readers Edition", "Margot Lee Shetterly", 9, 13, ["history", "science", "diversity"], []),
    ("Women in Science: 50 Fearless Pioneers", "Rachel Ignotofsky", 8, 14, ["science", "diversity", "history"], []),
    ("I Am Albert Einstein", "Brad Meltzer", 4, 8, ["science", "resilience", "creativity"], []),
    ("Who Was Albert Einstein?", "Jess M. Brallier", 8, 12, ["science", "history", "resilience"], []),
    ("Who Was Marie Curie?", "Megan Stine", 8, 12, ["science", "history", "resilience"], []),
    ("George's Secret Key to the Universe", "Lucy Hawking", 7, 11, ["science", "friendship", "courage"], []),
    ("The Magic School Bus: Lost in the Solar System", "Joanna Cole", 6, 10, ["science", "creativity", "problem_solving"], []),
    ("Hilo Book 1: The Boy Who Crashed to Earth", "Judd Winick", 7, 11, ["friendship", "science", "courage"], []),
    ("Nathan Hale's Hazardous Tales: One Dead Spy", "Nathan Hale", 8, 12, ["history", "courage", "problem_solving"], []),

    # ── History & Culture ─────────────────────────────────────────────────────
    ("Inside Out and Back Again", "Thanhha Lai", 8, 12, ["resilience", "diversity", "family"], ["Newbery Honor 2012"]),
    ("Front Desk", "Kelly Yang", 8, 12, ["diversity", "resilience", "family"], []),
    ("Three Keys", "Kelly Yang", 8, 12, ["diversity", "resilience", "courage"], []),
    ("Good Talk: A Memoir in Conversations", "Mira Jacob", 8, 12, ["diversity", "family", "history"], []),
    ("Stamped: Racism, Antiracism, and You", "Jason Reynolds", 10, 14, ["history", "diversity", "courage"], []),
    ("Genesis Begins Again", "Alicia D. Williams", 9, 12, ["diversity", "resilience", "family"], ["Newbery Honor 2020"]),
    ("American Street", "Ibi Zoboi", 12, 16, ["diversity", "family", "resilience"], []),
    ("The Watsons Go to Birmingham—1963", "Christopher Paul Curtis", 9, 12, ["history", "family", "courage"], ["Newbery Honor 1996"]),
    ("Bud, Not Buddy", "Christopher Paul Curtis", 9, 12, ["resilience", "family", "history"], ["Newbery Medal 2000"]),
    ("Locomotion", "Jacqueline Woodson", 9, 12, ["family", "resilience", "creativity"], ["Newbery Honor 2004"]),
    ("Brown Girl Dreaming", "Jacqueline Woodson", 9, 13, ["history", "family", "diversity"], ["Newbery Honor 2015"]),
    ("Show Way", "Jacqueline Woodson", 5, 9, ["history", "family", "diversity"], ["Caldecott Honor 2006"]),

    # ── Social Emotional / Feelings ───────────────────────────────────────────
    ("The Invisible String", "Patrice Karst", 3, 8, ["family", "emotions", "kindness"], []),
    ("When Sophie Gets Angry—Really, Really Angry", "Molly Bang", 3, 7, ["emotions", "family", "resilience"], ["Caldecott Honor 2000"]),
    ("In My Heart: A Book of Feelings", "Jo Witek", 2, 6, ["emotions", "family"], []),
    ("The Feelings Book", "Todd Parr", 2, 6, ["emotions", "diversity"], []),
    ("Today I Feel Silly, and Other Moods That Make My Day", "Jamie Lee Curtis", 3, 7, ["emotions", "family"], []),
    ("Grumpy Monkey", "Suzanne Lang", 3, 7, ["emotions", "friendship", "resilience"], []),
    ("Listening to My Body", "Gabi Garcia", 4, 8, ["emotions", "resilience", "kindness"], []),
    ("The Invisible String", "Patrice Karst", 3, 8, ["family", "emotions", "kindness"], []),
    ("Wonder", "R.J. Palacio", 8, 12, ["kindness", "friendship", "courage"], []),
    ("Restart", "Gordon Korman", 8, 12, ["kindness", "friendship", "resilience"], []),
    ("The One and Only Bob", "Katherine Applegate", 8, 12, ["friendship", "courage", "environment"], []),
    ("Ghost", "Jason Reynolds", 9, 13, ["resilience", "family", "friendship"], []),
    ("Patina", "Jason Reynolds", 9, 13, ["resilience", "family", "friendship"], []),
    ("Sunny", "Jason Reynolds", 9, 13, ["resilience", "family", "emotions"], []),
    ("Lu", "Jason Reynolds", 9, 13, ["resilience", "diversity", "friendship"], []),

    # ── Environment / Nature ──────────────────────────────────────────────────
    ("The Lorax", "Dr. Seuss", 4, 8, ["environment", "courage", "resilience"], []),
    ("Hoot", "Carl Hiaasen", 9, 13, ["environment", "courage", "problem_solving"], []),
    ("Flush", "Carl Hiaasen", 9, 13, ["environment", "courage", "family"], []),
    ("Scat", "Carl Hiaasen", 9, 13, ["environment", "problem_solving", "courage"], []),
    ("Seedfolks", "Paul Fleischman", 8, 12, ["diversity", "community", "environment"], []),
    ("The One and Only Ivan", "Katherine Applegate", 8, 12, ["courage", "friendship", "environment"], ["Newbery Medal 2013"]),
    ("Watership Down", "Richard Adams", 10, 14, ["courage", "friendship", "environment"], []),
    ("My Side of the Mountain", "Jean Craighead George", 9, 13, ["resilience", "environment", "courage"], ["Newbery Honor 1960"]),
    ("Julie of the Wolves", "Jean Craighead George", 9, 13, ["resilience", "environment", "courage"], ["Newbery Medal 1973"]),
    ("Island of the Blue Dolphins", "Scott O'Dell", 9, 12, ["resilience", "courage", "environment"], ["Newbery Medal 1961"]),
    ("Call of the Wild", "Jack London", 10, 14, ["courage", "resilience", "environment"], []),
    ("White Fang", "Jack London", 10, 14, ["courage", "resilience", "environment"], []),
    ("Old Yeller", "Fred Gipson", 8, 12, ["family", "courage", "resilience"], []),
    ("Ronia, the Robber's Daughter", "Astrid Lindgren", 8, 12, ["courage", "family", "environment"], []),
    ("The Sign of the Beaver", "Elizabeth George Speare", 9, 12, ["resilience", "history", "friendship"], ["Newbery Honor 1984"]),
]


# ── Google Books lookup ────────────────────────────────────────────────────────

async def fetch_google_books(client: httpx.AsyncClient, title: str, author: str):
    query = f'intitle:"{title}" inauthor:"{author.split()[0] if author else ""}"'
    params = {"q": query, "maxResults": 1, "printType": "books"}
    if GOOGLE_BOOKS_KEY:
        params["key"] = GOOGLE_BOOKS_KEY
    try:
        r = await client.get(
            "https://www.googleapis.com/books/v1/volumes",
            params=params, timeout=10.0
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            return None
        info = items[0].get("volumeInfo", {})
        isbn_13, isbn_10 = None, None
        for id_obj in info.get("industryIdentifiers", []):
            if id_obj["type"] == "ISBN_13":
                isbn_13 = id_obj["identifier"]
            elif id_obj["type"] == "ISBN_10":
                isbn_10 = id_obj["identifier"]
        cover = (info.get("imageLinks") or {}).get("thumbnail")
        if cover:
            cover = cover.replace("http://", "https://").replace("zoom=1", "zoom=2")
        return {
            "google_books_id": items[0].get("id"),
            "isbn_13": isbn_13,
            "isbn_10": isbn_10,
            "description": info.get("description"),
            "page_count": info.get("pageCount"),
            "cover_url": cover,
            "published_year": int(info.get("publishedDate", "0")[:4]) if info.get("publishedDate") else None,
            "publisher": info.get("publisher"),
            "genres": info.get("categories", []),
        }
    except Exception:
        return None


# ── Claude goal classification ──────────────────────────────────────────────────

async def classify_goals_with_claude(client, title: str, author: str, description: str, seed_goals: list) -> list:
    """Use Claude Haiku to validate/extend goals from description."""
    if not ANTHROPIC_API_KEY or not description:
        return seed_goals

    prompt = f"""Children's book: "{title}" by {author}

Description: {description[:600]}

Current tags: {seed_goals}

From this list of learning goals, pick the 2-4 that best fit this book:
kindness, courage, friendship, emotions, science, history, diversity, resilience, problem_solving, environment, family, creativity

Return ONLY a JSON array of goal strings. Example: ["courage", "friendship"]
No explanation, just the JSON array."""

    try:
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text.strip()
        # Extract JSON array
        m = re.search(r'\[.*?\]', text, re.DOTALL)
        if m:
            goals = json.loads(m.group())
            validated = [g for g in goals if g in VALID_GOALS]
            return validated if validated else seed_goals
    except Exception:
        pass
    return seed_goals


# ── Database operations ───────────────────────────────────────────────────────

async def book_exists(conn, title: str):
    """Check if book exists by title (case-insensitive). Returns (exists, row)."""
    row = await conn.fetchrow(
        "SELECT id, cover_url, description, learning_goals FROM books WHERE LOWER(title) = LOWER($1)",
        title
    )
    return (row is not None), row


async def insert_or_enrich(conn, book: dict) -> str:
    """Insert new book or enrich existing one with missing metadata. Returns 'inserted'|'enriched'|'skipped'."""
    exists, existing = await book_exists(conn, book["title"])

    if exists:
        updates = {}
        if not existing["cover_url"] and book.get("cover_url"):
            updates["cover_url"] = book["cover_url"]
        if not existing["description"] and book.get("description"):
            updates["description"] = book["description"]
        # Merge learning goals
        current_goals = json.loads(existing["learning_goals"] or "[]")
        new_goals = book.get("learning_goals", [])
        merged = list(set(current_goals) | set(new_goals))
        if set(merged) != set(current_goals):
            updates["learning_goals"] = json.dumps(merged)

        if updates:
            set_clause = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates))
            vals = list(updates.values())
            await conn.execute(
                f"UPDATE books SET {set_clause} WHERE LOWER(title) = LOWER($1)",
                book["title"], *vals
            )
            return "enriched"
        return "skipped"

    # Insert new book
    try:
        await conn.execute("""
            INSERT INTO books (
                title, author, age_min, age_max,
                cover_url, description, page_count,
                published_year, publisher, genres,
                isbn_13, isbn_10, google_books_id,
                learning_goals, is_children_book, awards,
                is_series, has_violence, has_scary_content, has_adult_themes,
                language
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,
                $11,$12,$13,$14::jsonb,TRUE,$15::jsonb,
                FALSE,FALSE,FALSE,FALSE,'en'
            )
            ON CONFLICT DO NOTHING
        """,
            book["title"], book["author"], book["age_min"], book["age_max"],
            book.get("cover_url"), book.get("description"), book.get("page_count"),
            book.get("published_year"), book.get("publisher"),
            json.dumps(book.get("genres", [])),
            book.get("isbn_13"), book.get("isbn_10"), book.get("google_books_id"),
            json.dumps(book.get("learning_goals", [])),
            json.dumps(book.get("awards", []))
        )
        return "inserted"
    except Exception as e:
        print(f"    ❌ Insert failed for '{book['title']}': {e}")
        return "error"


# ── Expansion Pack: Coretta Scott King, Pura Belpré, Sibert, Graphic Novels ──

CURATED_BOOKS += [
    # ── Coretta Scott King Award (Author) ────────────────────────────────────
    ("Elijah of Buxton", "Christopher Paul Curtis", 9, 12, ["history", "courage", "resilience"], ["Coretta Scott King Award 2008"]),
    ("One Crazy Summer", "Rita Williams-Garcia", 9, 12, ["family", "history", "resilience"], ["Coretta Scott King Award 2011"]),
    ("P.S. Be Eleven", "Rita Williams-Garcia", 9, 12, ["family", "resilience", "emotions"], ["Coretta Scott King Award 2014"]),
    ("Copper Sun", "Sharon Draper", 10, 14, ["history", "courage", "resilience"], ["Coretta Scott King Award 2007"]),
    ("Forged by Fire", "Sharon Draper", 10, 14, ["resilience", "family", "courage"], ["Coretta Scott King Award 1998"]),
    ("Miracle's Boys", "Jacqueline Woodson", 10, 14, ["family", "resilience", "emotions"], ["Coretta Scott King Award 2001"]),
    ("The First Part Last", "Angela Johnson", 12, 16, ["family", "resilience", "emotions"], ["Coretta Scott King Award 2004"]),
    ("Toning the Sweep", "Angela Johnson", 10, 14, ["family", "resilience", "history"], ["Coretta Scott King Award 1994"]),
    ("Slam!", "Walter Dean Myers", 10, 14, ["resilience", "family", "friendship"], ["Coretta Scott King Award 1997"]),
    ("Fallen Angels", "Walter Dean Myers", 12, 16, ["history", "courage", "resilience"], ["Coretta Scott King Award 1989"]),
    ("Now Is Your Time!", "Walter Dean Myers", 10, 14, ["history", "diversity", "courage"], ["Coretta Scott King Award 1992"]),
    ("Fast Sam, Cool Clyde, and Stuff", "Walter Dean Myers", 10, 13, ["friendship", "resilience", "family"], ["Coretta Scott King Honor 1976"]),
    ("The Dark-Thirty: Southern Tales of the Supernatural", "Patricia C. McKissack", 9, 13, ["history", "courage", "creativity"], ["Coretta Scott King Award 1993", "Newbery Honor 1993"]),
    ("Road to Memphis", "Mildred D. Taylor", 10, 14, ["history", "courage", "resilience"], ["Coretta Scott King Award 1991"]),
    ("Let the Circle Be Unbroken", "Mildred D. Taylor", 10, 14, ["history", "family", "resilience"], ["Coretta Scott King Award 1982"]),
    ("Song of the Trees", "Mildred D. Taylor", 8, 12, ["history", "family", "courage"], ["Coretta Scott King Award 1976"]),
    ("The Friendship", "Mildred D. Taylor", 8, 12, ["history", "courage", "resilience"], ["Coretta Scott King Award 1988"]),
    ("Sweet Whispers, Brother Rush", "Virginia Hamilton", 10, 14, ["family", "emotions", "resilience"], ["Coretta Scott King Award 1983", "Newbery Honor 1983"]),
    ("Her Stories: African American Folktales", "Virginia Hamilton", 8, 12, ["history", "diversity", "creativity"], ["Coretta Scott King Award 1996"]),
    ("Justin and the Best Biscuits in the World", "Mildred Pitts Walter", 8, 12, ["family", "history", "resilience"], ["Coretta Scott King Award 1987"]),
    ("Look Both Ways: A Tale Told in Ten Blocks", "Jason Reynolds", 9, 12, ["kindness", "diversity", "friendship"], ["Coretta Scott King Honor 2020"]),
    ("All American Boys", "Jason Reynolds", 12, 16, ["history", "courage", "diversity"], ["Coretta Scott King Honor 2016"]),
    ("Long Way Down", "Jason Reynolds", 12, 16, ["resilience", "emotions", "history"], ["Coretta Scott King Honor 2018"]),
    ("Jabari Jumps", "Gaia Cornwall", 3, 7, ["courage", "family", "emotions"], ["Coretta Scott King Honor 2018"]),
    ("Each Kindness", "Jacqueline Woodson", 5, 9, ["kindness", "emotions", "friendship"], ["Coretta Scott King Honor 2013"]),
    ("Show Way", "Jacqueline Woodson", 5, 9, ["history", "family", "diversity"], ["Coretta Scott King Honor 2006"]),
    ("The Other Side", "Jacqueline Woodson", 4, 8, ["diversity", "kindness", "history"], ["Coretta Scott King Honor 2002"]),
    ("Coming On Home Soon", "Jacqueline Woodson", 4, 8, ["family", "history", "emotions"], ["Caldecott Honor 2005"]),
    ("We Are the Ship: The Story of Negro League Baseball", "Kadir Nelson", 9, 13, ["history", "diversity", "resilience"], ["Coretta Scott King Award 2009", "Sibert Honor 2009"]),
    ("Moses: When Harriet Tubman Led Her People to Freedom", "Carole Boston Weatherford", 5, 9, ["history", "courage", "diversity"], ["Caldecott Honor 2007", "Coretta Scott King Honor 2007"]),
    ("Ruth and the Green Book", "Calvin Alexander Ramsey", 5, 9, ["history", "diversity", "family"], []),
    ("Freedom on the Menu: The Greensboro Sit-Ins", "Carole Boston Weatherford", 5, 9, ["history", "courage", "diversity"], []),
    ("Voice of Freedom: Fannie Lou Hamer", "Carole Boston Weatherford", 7, 11, ["history", "courage", "diversity"], ["Sibert Honor 2016"]),
    ("Booked", "Kwame Alexander", 9, 12, ["resilience", "family", "friendship"], []),
    ("Rebound", "Kwame Alexander", 9, 12, ["resilience", "family", "emotions"], []),
    ("Swing", "Kwame Alexander", 9, 12, ["friendship", "resilience", "creativity"], []),
    ("Becoming Muhammad Ali", "James Patterson", 9, 13, ["history", "resilience", "courage"], []),
    ("Genesis Begins Again", "Alicia D. Williams", 9, 12, ["resilience", "diversity", "family"], ["Newbery Honor 2020", "Coretta Scott King Honor 2020"]),
    ("Saturday", "Oge Mora", 3, 7, ["family", "resilience", "kindness"], ["Caldecott Honor 2020"]),
    ("Thank You, Omu!", "Oge Mora", 3, 7, ["kindness", "family", "diversity"], []),

    # ── Pura Belpré Award (Latino/Latina authors/illustrators) ───────────────
    ("Return to Sender", "Julia Alvarez", 9, 12, ["diversity", "family", "resilience"], ["Pura Belpré Award 2010"]),
    ("Before We Were Free", "Julia Alvarez", 10, 14, ["history", "courage", "resilience"], ["Pura Belpré Award 2004"]),
    ("How Tía Lola Came to Visit Stay", "Julia Alvarez", 8, 12, ["family", "diversity", "kindness"], []),
    ("The Only Road", "Alexandra Diaz", 10, 14, ["resilience", "family", "courage"], ["Pura Belpré Honor 2017"]),
    ("Becoming Naomi León", "Pam Muñoz Ryan", 8, 12, ["family", "resilience", "courage"], ["Pura Belpré Honor 2005"]),
    ("Riding Freedom", "Pam Muñoz Ryan", 8, 12, ["courage", "history", "resilience"], []),
    ("Celia Cruz, Queen of Salsa", "Veronica Chambers", 5, 9, ["history", "diversity", "creativity"], []),
    ("Under the Mesquite", "Guadalupe Garcia McCall", 10, 14, ["family", "resilience", "diversity"], ["Pura Belpré Award 2012"]),
    ("The Poet X", "Elizabeth Acevedo", 12, 16, ["diversity", "resilience", "creativity"], ["Pura Belpré Award 2019"]),
    ("With the Fire on Every Side", "Elizabeth Acevedo", 12, 16, ["diversity", "family", "resilience"], []),
    ("Furia", "Yamile Saied Méndez", 12, 16, ["resilience", "courage", "diversity"], ["Pura Belpré Award 2021"]),
    ("Alma and How She Got Her Name", "Juana Martinez-Neal", 3, 7, ["family", "diversity", "creativity"], ["Caldecott Honor 2019", "Pura Belpré Award 2019"]),
    ("Dreamers", "Yuyi Morales", 3, 7, ["family", "diversity", "resilience"], ["Pura Belpré Award 2019"]),
    ("Niño Wrestles the World", "Yuyi Morales", 3, 7, ["courage", "creativity", "family"], ["Pura Belpré Award 2014"]),
    ("Just a Minute: A Trickster Tale", "Yuyi Morales", 3, 7, ["creativity", "family", "problem_solving"], ["Pura Belpré Award 2004"]),
    ("Harvesting Hope: The Story of Cesar Chavez", "Kathleen Krull", 5, 9, ["history", "courage", "resilience"], ["Pura Belpré Honor 2004"]),
    ("Lowriders in Space", "Cathy Camper", 7, 11, ["creativity", "friendship", "science"], ["Pura Belpré Honor 2015"]),
    ("The Surrender Tree: Poems of Cuba's Struggle for Freedom", "Margarita Engle", 10, 14, ["history", "courage", "resilience"], ["Pura Belpré Award 2009", "Newbery Honor 2009"]),
    ("Hurricane Child", "Kheryn Callender", 9, 13, ["resilience", "family", "diversity"], ["Pura Belpré Award 2019"]),
    ("Merci Suárez Can't Dance", "Meg Medina", 9, 12, ["family", "resilience", "emotions"], []),
    ("¡Olinguito, de la A a la Z!", "Lulu Delacre", 4, 8, ["science", "diversity", "creativity"], ["Pura Belpré Award 2017"]),

    # ── Sibert Medal (Nonfiction for children) ──────────────────────────────
    ("Bomb: The Race to Build—and Steal—the World's Most Dangerous Weapon", "Steve Sheinkin", 9, 14, ["history", "science", "courage"], ["Sibert Medal 2013", "Newbery Honor 2013"]),
    ("Lincoln's Grave Robbers", "Steve Sheinkin", 9, 13, ["history", "problem_solving", "courage"], ["Sibert Honor 2013"]),
    ("Most Dangerous: Daniel Ellsberg and the Secret History of the Vietnam War", "Steve Sheinkin", 10, 14, ["history", "courage", "resilience"], ["Sibert Medal 2016"]),
    ("Port Chicago 50: Disaster, Mutiny, and the Fight for Civil Rights", "Steve Sheinkin", 10, 14, ["history", "courage", "diversity"], ["Sibert Honor 2015"]),
    ("Undefeated: Jim Thorpe and the Carlisle Indian School Football Team", "Steve Sheinkin", 9, 13, ["history", "resilience", "courage"], ["Sibert Medal 2018"]),
    ("Claudette Colvin: Twice Toward Justice", "Phillip Hoose", 10, 14, ["history", "courage", "diversity"], ["Sibert Medal 2010", "Newbery Honor 2010"]),
    ("The Great and Only Barnum", "Candace Fleming", 9, 13, ["history", "creativity", "courage"], ["Sibert Honor 2010"]),
    ("The Family Romanov: Murder, Rebellion, and the Fall of Imperial Russia", "Candace Fleming", 10, 14, ["history", "resilience", "courage"], ["Sibert Medal 2015"]),
    ("Titanic: Voices from the Disaster", "Deborah Hopkinson", 9, 13, ["history", "resilience", "courage"], ["Sibert Honor 2013"]),
    ("When Marian Sang", "Pam Muñoz Ryan", 6, 10, ["history", "courage", "diversity"], ["Sibert Honor 2003"]),
    ("An American Plague: The True and Terrifying Story of the Yellow Fever Epidemic of 1793", "Jim Murphy", 9, 13, ["history", "science", "resilience"], ["Sibert Medal 2004", "Newbery Honor 2004"]),
    ("Trapped: How the World Rescued 33 Miners from 2,000 Feet Below the Chilean Desert", "Marc Aronson", 9, 13, ["resilience", "courage", "problem_solving"], ["Sibert Honor 2012"]),
    ("Women in Science", "Rachel Ignotofsky", 8, 14, ["science", "diversity", "history"], []),
    ("Rad American Women A-Z", "Kate Schatz", 8, 14, ["history", "courage", "diversity"], []),
    ("I Am Malala: How One Girl Stood Up for Education", "Malala Yousafzai", 10, 14, ["courage", "history", "resilience"], []),
    ("The Boy Who Harnessed the Wind", "William Kamkwamba", 9, 13, ["resilience", "science", "courage"], []),
    ("Claudette Colvin: Twice Toward Justice", "Phillip Hoose", 10, 14, ["history", "courage", "diversity"], []),
    ("Giant Squid: Searching for a Sea Monster", "Mary M. Cerullo", 7, 11, ["science", "environment", "problem_solving"], []),
    ("Eruption!: Volcanoes and the Science of Saving Lives", "Elizabeth Rusch", 8, 12, ["science", "resilience", "problem_solving"], ["Sibert Honor 2013"]),
    ("Eyes Wide Open: Going Behind the Environmental Headlines", "Paul Fleischman", 10, 14, ["environment", "history", "problem_solving"], []),
    ("The Whalers", "Katherine Kirkpatrick", 9, 13, ["history", "environment", "courage"], []),
    ("Tracking Trash: Flotsam, Jetsam, and the Science of Ocean Motion", "Loree Griffin Burns", 8, 12, ["science", "environment", "problem_solving"], ["Sibert Honor 2008"]),

    # ── Graphic Novels / Illustrated novels ────────────────────────────────
    ("Smile", "Raina Telgemeier", 8, 12, ["resilience", "friendship", "emotions"], []),
    ("Drama", "Raina Telgemeier", 8, 12, ["creativity", "friendship", "diversity"], []),
    ("Sisters", "Raina Telgemeier", 8, 12, ["family", "resilience", "emotions"], []),
    ("Guts", "Raina Telgemeier", 8, 12, ["emotions", "resilience", "friendship"], []),
    ("El Deafo", "Cece Bell", 8, 12, ["resilience", "friendship", "diversity"], ["Newbery Honor 2015", "Eisner Award"]),
    ("Roller Girl", "Victoria Jamieson", 8, 12, ["resilience", "friendship", "courage"], ["Newbery Honor 2016"]),
    ("Real Friends", "Shannon Hale", 8, 12, ["friendship", "resilience", "emotions"], []),
    ("Best Friends", "Shannon Hale", 8, 12, ["friendship", "resilience", "emotions"], []),
    ("Amulet Book 1: The Stonekeeper", "Kazu Kibuishi", 8, 12, ["courage", "family", "problem_solving"], []),
    ("Class Act", "Jerry Craft", 8, 12, ["diversity", "friendship", "resilience"], []),
    ("The Bad Guys", "Aaron Blabey", 6, 9, ["friendship", "courage", "problem_solving"], []),
    ("Ghosts", "Raina Telgemeier", 8, 12, ["family", "emotions", "diversity"], []),
    ("American Born Chinese", "Gene Luen Yang", 10, 14, ["diversity", "resilience", "family"], ["Printz Honor", "Eisner Award"]),
    ("Secret Coders", "Gene Luen Yang", 8, 12, ["science", "problem_solving", "friendship"], []),
    ("Anya's Ghost", "Vera Brosgol", 10, 14, ["resilience", "friendship", "emotions"], ["Eisner Award"]),
    ("Cardboard Kingdom", "Chad Sell", 8, 12, ["creativity", "friendship", "diversity"], []),
    ("Pashmina", "Nidhi Chanani", 8, 12, ["family", "diversity", "resilience"], []),
    ("Almost American Girl", "Robin Ha", 10, 14, ["diversity", "friendship", "resilience"], []),
    ("Allergic", "Megan Wagner Lloyd", 8, 12, ["resilience", "family", "emotions"], []),
    ("Nathan Hale's Hazardous Tales: Donner Dinner Party", "Nathan Hale", 8, 12, ["history", "resilience", "courage"], []),

    # ── More Newbery/Caldecott we missed ─────────────────────────────────────
    ("The Summer of the Swans", "Betsy Byars", 9, 12, ["family", "resilience", "kindness"], ["Newbery Medal 1971"]),
    ("Call It Courage", "Armstrong Sperry", 8, 12, ["courage", "resilience", "environment"], ["Newbery Medal 1941"]),
    ("King of the Wind", "Marguerite Henry", 8, 12, ["resilience", "history", "courage"], ["Newbery Medal 1949"]),
    ("Misty of Chincoteague", "Marguerite Henry", 8, 12, ["resilience", "family", "environment"], []),
    ("Witch of Blackbird Pond", "Elizabeth George Speare", 10, 14, ["history", "courage", "resilience"], ["Newbery Medal 1959"]),
    ("The Bronze Bow", "Elizabeth George Speare", 10, 14, ["history", "courage", "resilience"], ["Newbery Medal 1962"]),
    ("Rifles for Watie", "Harold Keith", 10, 14, ["history", "courage", "resilience"], ["Newbery Medal 1958"]),
    ("The High King", "Lloyd Alexander", 9, 13, ["courage", "friendship", "history"], ["Newbery Medal 1969"]),
    ("The Book of Three", "Lloyd Alexander", 9, 13, ["courage", "friendship", "problem_solving"], []),
    ("The Black Cauldron", "Lloyd Alexander", 9, 13, ["courage", "friendship", "resilience"], ["Newbery Honor 1966"]),
    ("Up a Road Slowly", "Irene Hunt", 10, 14, ["resilience", "family", "emotions"], ["Newbery Medal 1967"]),
    ("My Brother Sam Is Dead", "James Lincoln Collier", 10, 14, ["history", "courage", "family"], ["Newbery Honor 1975"]),
    ("The Egypt Game", "Zilpha Keatley Snyder", 9, 12, ["problem_solving", "friendship", "creativity"], ["Newbery Honor 1968"]),
    ("Below the Root", "Zilpha Keatley Snyder", 9, 12, ["courage", "problem_solving", "creativity"], []),
    ("Strawberry Girl", "Lois Lenski", 8, 12, ["resilience", "family", "history"], ["Newbery Medal 1946"]),
    ("Amos Fortune, Free Man", "Elizabeth Yates", 9, 13, ["history", "courage", "resilience"], ["Newbery Medal 1951"]),
    ("Carry On, Mr. Bowditch", "Jean Lee Latham", 9, 13, ["resilience", "science", "history"], ["Newbery Medal 1956"]),
    ("The Wheel on the School", "Meindert DeJong", 8, 12, ["courage", "community", "problem_solving"], ["Newbery Medal 1955"]),
    ("I, Juan de Pareja", "Elizabeth Borton de Treviño", 9, 13, ["history", "courage", "resilience"], ["Newbery Medal 1966"]),
    ("The Headless Cupid", "Zilpha Keatley Snyder", 9, 12, ["family", "problem_solving", "creativity"], ["Newbery Honor 1972"]),
    ("Rabbit Hill", "Robert Lawson", 7, 11, ["environment", "family", "kindness"], ["Newbery Medal 1945"]),
    ("The Twenty-One Balloons", "William Pène du Bois", 9, 12, ["creativity", "science", "problem_solving"], ["Newbery Medal 1948"]),
    ("Merry Adventures of Robin Hood", "Howard Pyle", 9, 14, ["courage", "kindness", "history"], []),

    # ── International Children's Classics ──────────────────────────────────
    ("Heidi", "Johanna Spyri", 7, 12, ["family", "resilience", "environment"], []),
    ("Pinocchio", "Carlo Collodi", 6, 10, ["courage", "resilience", "family"], []),
    ("Bambi", "Felix Salten", 7, 11, ["environment", "family", "resilience"], []),
    ("Finn Family Moomintroll", "Tove Jansson", 7, 11, ["friendship", "creativity", "environment"], []),
    ("Moomin and the Great Flood", "Tove Jansson", 5, 9, ["family", "courage", "resilience"], []),
    ("Emil of Lönneberga", "Astrid Lindgren", 6, 10, ["creativity", "family", "resilience"], []),
    ("The Brothers Lionheart", "Astrid Lindgren", 9, 13, ["courage", "family", "resilience"], []),
    ("Karlsson-on-the-Roof", "Astrid Lindgren", 6, 10, ["creativity", "friendship", "family"], []),
    ("The Neverending Story", "Michael Ende", 9, 13, ["courage", "creativity", "resilience"], []),
    ("Momo", "Michael Ende", 9, 13, ["courage", "friendship", "problem_solving"], []),
    ("The Flying Classroom", "Erich Kästner", 9, 12, ["friendship", "courage", "family"], []),
    ("Lottie and Lisa", "Erich Kästner", 8, 12, ["family", "problem_solving", "courage"], []),
    ("The Little Witch", "Otfried Preussler", 7, 11, ["courage", "kindness", "problem_solving"], []),
    ("The Robber Hotzenplotz", "Otfried Preussler", 6, 10, ["problem_solving", "courage", "friendship"], []),
    ("The Wonderful Adventures of Nils", "Selma Lagerlöf", 9, 13, ["courage", "environment", "resilience"], []),
    ("Anne of Avonlea", "L.M. Montgomery", 9, 14, ["creativity", "friendship", "resilience"], []),
    ("Emily of New Moon", "L.M. Montgomery", 9, 13, ["creativity", "family", "resilience"], []),
    ("Swallows and Amazons", "Arthur Ransome", 8, 13, ["friendship", "courage", "problem_solving"], []),
    ("The Borrowers", "Mary Norton", 7, 11, ["courage", "creativity", "problem_solving"], []),
    ("The Sword in the Stone", "T.H. White", 10, 14, ["courage", "history", "problem_solving"], []),
    ("Tom's Midnight Garden", "Philippa Pearce", 9, 12, ["friendship", "family", "creativity"], ["Carnegie Medal"]),
    ("The Dark Is Rising", "Susan Cooper", 9, 13, ["courage", "history", "problem_solving"], ["Newbery Honor 1974"]),
    ("Over Sea, Under Stone", "Susan Cooper", 9, 13, ["courage", "problem_solving", "history"], []),
    ("Bedknob and Broomstick", "Mary Norton", 7, 11, ["creativity", "problem_solving", "courage"], []),
    ("The Enchanted Castle", "E. Nesbit", 8, 12, ["creativity", "problem_solving", "friendship"], []),
    ("Five Children and It", "E. Nesbit", 8, 12, ["creativity", "problem_solving", "family"], []),
    ("The Railway Children", "E. Nesbit", 8, 12, ["family", "resilience", "courage"], []),
    ("The Story of the Treasure Seekers", "E. Nesbit", 8, 12, ["problem_solving", "family", "creativity"], []),

    # ── More popular series starters ────────────────────────────────────────
    ("Wings of Fire: The Dragonet Prophecy", "Tui T. Sutherland", 8, 12, ["courage", "friendship", "resilience"], []),
    ("The Ranger's Apprentice: The Ruins of Gorlan", "John Flanagan", 10, 14, ["courage", "friendship", "resilience"], []),
    ("Fablehaven", "Brandon Mull", 9, 12, ["courage", "family", "problem_solving"], []),
    ("The Land of Stories: The Wishing Spell", "Chris Colfer", 8, 12, ["courage", "creativity", "family"], []),
    ("Septimus Heap: Magyk", "Angie Sage", 8, 12, ["courage", "family", "problem_solving"], []),
    ("The Kane Chronicles: The Red Pyramid", "Rick Riordan", 9, 12, ["courage", "history", "problem_solving"], []),
    ("Magnus Chase and the Gods of Asgard: The Sword of Summer", "Rick Riordan", 9, 12, ["courage", "friendship", "history"], []),
    ("The Heroes of Olympus: The Lost Hero", "Rick Riordan", 9, 12, ["courage", "friendship", "resilience"], []),
    ("I Survived: The Sinking of the Titanic, 1912", "Lauren Tarshis", 7, 10, ["courage", "history", "resilience"], []),
    ("Timmy Failure: Mistakes Were Made", "Stephan Pastis", 8, 12, ["problem_solving", "friendship", "creativity"], []),
    ("Dork Diaries: Tales from a Not-So-Fabulous Life", "Rachel Renée Russell", 8, 12, ["friendship", "resilience", "emotions"], []),
    ("Middle School: The Worst Years of My Life", "James Patterson", 8, 12, ["resilience", "creativity", "friendship"], []),
    ("The 39 Clues: The Maze of Bones", "Rick Riordan", 9, 12, ["problem_solving", "courage", "history"], []),
    ("Gregor the Overlander", "Suzanne Collins", 8, 12, ["courage", "family", "resilience"], []),
    ("The Underland Chronicles", "Suzanne Collins", 8, 12, ["courage", "family", "resilience"], []),
    ("Hilo Book 2: Saving the World and Beyond", "Judd Winick", 7, 11, ["friendship", "science", "courage"], []),
    ("The Unwanteds", "Lisa McMann", 9, 12, ["courage", "creativity", "friendship"], []),
    ("Spirit Animals: Wild Born", "Brandon Mull", 8, 12, ["courage", "friendship", "environment"], []),
    ("Guardians of Ga'Hoole: The Capture", "Kathryn Lasky", 8, 12, ["courage", "friendship", "resilience"], []),
    ("Warrior Cats: Into the Wild", "Erin Hunter", 9, 12, ["courage", "resilience", "family"], []),
    ("Eragon", "Christopher Paolini", 12, 16, ["courage", "friendship", "resilience"], []),
    ("The Ranger's Apprentice: The Ruins of Gorlan", "John Flanagan", 10, 14, ["courage", "friendship", "resilience"], []),

    # ── Poetry for children ─────────────────────────────────────────────────
    ("Where the Sidewalk Ends", "Shel Silverstein", 6, 12, ["creativity", "emotions", "problem_solving"], []),
    ("A Light in the Attic", "Shel Silverstein", 6, 12, ["creativity", "emotions", "resilience"], []),
    ("Falling Up", "Shel Silverstein", 6, 12, ["creativity", "emotions", "problem_solving"], []),
    ("The Giving Tree", "Shel Silverstein", 4, 10, ["kindness", "family", "resilience"], []),
    ("Honey, I Love and Other Love Poems", "Eloise Greenfield", 5, 9, ["family", "kindness", "emotions"], ["Coretta Scott King Honor"]),
    ("Bronzeville Boys and Girls", "Gwendolyn Brooks", 5, 9, ["diversity", "emotions", "family"], []),
    ("Brown Girl Dreaming", "Jacqueline Woodson", 9, 13, ["history", "family", "diversity"], ["Newbery Honor 2015", "Coretta Scott King Award 2015"]),
    ("Locomotion", "Jacqueline Woodson", 9, 12, ["family", "resilience", "creativity"], ["Newbery Honor 2004", "Coretta Scott King Honor 2004"]),
    ("Love That Dog", "Sharon Creech", 8, 12, ["emotions", "creativity", "resilience"], []),
    ("Hate That Cat", "Sharon Creech", 8, 12, ["emotions", "creativity", "resilience"], []),
    ("The Random House Book of Poetry for Children", "Jack Prelutsky", 5, 12, ["creativity", "emotions", "kindness"], []),
    ("Something Big Has Been Here", "Jack Prelutsky", 5, 10, ["creativity", "emotions", "problem_solving"], []),
    ("A Pizza the Size of the Sun", "Jack Prelutsky", 5, 10, ["creativity", "emotions"], []),

    # ── More picture books & early readers ─────────────────────────────────
    ("No, David!", "David Shannon", 3, 6, ["emotions", "family", "resilience"], ["Caldecott Honor 1999"]),
    ("A Bad Case of Stripes", "David Shannon", 4, 8, ["resilience", "diversity", "emotions"], []),
    ("The Napping House", "Audrey Wood", 2, 6, ["family", "creativity", "emotions"], []),
    ("Heckedy Peg", "Audrey Wood", 4, 8, ["courage", "family", "problem_solving"], []),
    ("King Bidgood's in the Bathtub", "Audrey Wood", 3, 7, ["problem_solving", "creativity", "family"], ["Caldecott Honor 1986"]),
    ("Swimmy", "Leo Lionni", 3, 7, ["friendship", "problem_solving", "courage"], ["Caldecott Honor 1964"]),
    ("Frederick", "Leo Lionni", 3, 7, ["creativity", "resilience", "family"], []),
    ("Alexander and the Wind-Up Mouse", "Leo Lionni", 3, 7, ["friendship", "kindness", "emotions"], ["Caldecott Honor 1970"]),
    ("Inch by Inch", "Leo Lionni", 3, 7, ["creativity", "problem_solving", "resilience"], ["Caldecott Honor 1961"]),
    ("Fish is Fish", "Leo Lionni", 3, 7, ["friendship", "diversity", "resilience"], []),
    ("Little Blue and Little Yellow", "Leo Lionni", 3, 6, ["friendship", "diversity", "emotions"], []),
    ("Harry the Dirty Dog", "Gene Zion", 3, 7, ["family", "problem_solving", "emotions"], []),
    ("Curious George", "H.A. Rey", 3, 6, ["curiosity", "problem_solving", "creativity"], []),
    ("Madeline", "Ludwig Bemelmans", 4, 8, ["courage", "family", "resilience"], ["Caldecott Honor 1940"]),
    ("Paddington Bear", "Michael Bond", 6, 10, ["kindness", "family", "resilience"], []),
    ("The House at Pooh Corner", "A.A. Milne", 5, 10, ["friendship", "family", "creativity"], []),
    ("Fly Guy Presents: Space", "Tedd Arnold", 5, 8, ["science", "friendship", "creativity"], []),
    ("Noodlehead Nightmares", "Tedd Arnold", 5, 8, ["problem_solving", "friendship", "creativity"], []),
    ("Diary of a Worm: Teacher's Pet", "Doreen Cronin", 4, 8, ["friendship", "diversity", "resilience"], []),
    ("Click, Clack, Quackity-Quack", "Doreen Cronin", 3, 7, ["creativity", "problem_solving", "friendship"], []),
    ("The Pigeon Wants a Puppy!", "Mo Willems", 2, 6, ["emotions", "family", "problem_solving"], []),
    ("The Pigeon Finds a Hot Dog!", "Mo Willems", 2, 6, ["emotions", "friendship", "problem_solving"], []),
    ("Waiting Is Not Easy!", "Mo Willems", 2, 6, ["emotions", "resilience", "friendship"], []),
    ("I Am Invited to a Party!", "Mo Willems", 4, 8, ["friendship", "emotions", "kindness"], []),
    ("There Is a Bird on Your Head!", "Mo Willems", 4, 8, ["friendship", "problem_solving", "emotions"], []),
    ("Frog and Toad All Year", "Arnold Lobel", 5, 8, ["friendship", "kindness", "resilience"], []),
    ("Grasshopper on the Road", "Arnold Lobel", 5, 8, ["problem_solving", "courage", "friendship"], []),
    ("Mouse Tales", "Arnold Lobel", 5, 8, ["creativity", "family", "friendship"], ["Caldecott Honor 1973"]),
    ("Owl at Home", "Arnold Lobel", 5, 8, ["emotions", "problem_solving", "creativity"], []),
    ("Mouse Soup", "Arnold Lobel", 5, 8, ["problem_solving", "creativity", "courage"], []),
    ("Caps for Sale", "Esphyr Slobodkina", 3, 7, ["problem_solving", "resilience", "courage"], []),
    ("Make Way for Ducklings", "Robert McCloskey", 3, 7, ["family", "courage", "problem_solving"], ["Caldecott Medal 1942"]),
    ("Blueberries for Sal", "Robert McCloskey", 3, 7, ["family", "environment", "courage"], ["Caldecott Honor 1949"]),
    ("One Morning in Maine", "Robert McCloskey", 3, 7, ["family", "resilience", "problem_solving"], ["Caldecott Honor 1953"]),
    ("Time of Wonder", "Robert McCloskey", 4, 8, ["environment", "family", "creativity"], ["Caldecott Medal 1958"]),
    ("The Story About Ping", "Marjorie Flack", 3, 7, ["family", "courage", "resilience"], []),
    ("Mike Mulligan and His Steam Shovel", "Virginia Lee Burton", 4, 8, ["resilience", "problem_solving", "creativity"], []),
    ("The Little House", "Virginia Lee Burton", 3, 7, ["history", "environment", "family"], ["Caldecott Medal 1943"]),
    ("Katy and the Big Snow", "Virginia Lee Burton", 3, 7, ["resilience", "problem_solving", "courage"], []),
    ("Lentil", "Robert McCloskey", 4, 8, ["creativity", "courage", "kindness"], []),
    ("The Poky Little Puppy", "Janette Sebring Lowrey", 2, 5, ["resilience", "family", "problem_solving"], []),
    ("The Saggy Baggy Elephant", "Kathryn Byron Jackson", 2, 5, ["resilience", "diversity", "family"], []),
    ("Scuffy the Tugboat", "Gertrude Crampton", 2, 5, ["courage", "resilience", "family"], []),
    ("Pat the Bunny", "Dorothy Kunhardt", 0, 2, ["family", "emotions"], []),
    ("Goodnight Gorilla", "Peggy Rathmann", 2, 5, ["creativity", "problem_solving", "family"], []),
    ("The Snowy Day", "Ezra Jack Keats", 3, 6, ["diversity", "creativity", "family"], ["Caldecott Medal 1963"]),
    ("Peter's Chair", "Ezra Jack Keats", 3, 6, ["family", "emotions", "resilience"], []),
    ("A Letter to Amy", "Ezra Jack Keats", 3, 7, ["friendship", "kindness", "emotions"], []),
    ("Goggles!", "Ezra Jack Keats", 4, 8, ["courage", "diversity", "problem_solving"], ["Caldecott Honor 1970"]),
    ("Apt. 3", "Ezra Jack Keats", 4, 8, ["diversity", "kindness", "family"], []),
    ("Hi, Cat!", "Ezra Jack Keats", 3, 7, ["friendship", "kindness", "family"], []),
]

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    from anthropic import AsyncAnthropic
    conn = await asyncpg.connect(DB_URL)
    anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

    before = await conn.fetchval("SELECT COUNT(*) FROM books WHERE is_children_book = TRUE")
    print(f"BookMind Award Book Ingestion")
    print(f"Current children's books: {before}")
    print(f"Books to process: {len(CURATED_BOOKS)}")
    print(f"Google Books API: {'with key' if GOOGLE_BOOKS_KEY else 'keyless (rate-limited)'}")
    print(f"Claude goal classification: {'enabled' if anthropic_client else 'disabled'}\n")

    inserted = enriched = skipped = errors = 0
    last_request_time = 0

    async with httpx.AsyncClient() as http:
        # Deduplicate the curated list by title
        seen_titles = set()
        unique_books = []
        for entry in CURATED_BOOKS:
            t = entry[0].lower()
            if t not in seen_titles:
                seen_titles.add(t)
                unique_books.append(entry)

        print(f"Unique titles to process: {len(unique_books)}\n")

        for i, (title, author, age_min, age_max, seed_goals, awards) in enumerate(unique_books, 1):
            print(f"[{i:3}/{len(unique_books)}] {title[:50]}", end="", flush=True)

            # Rate-limit Google Books (max ~10 req/s without key)
            elapsed = time.time() - last_request_time
            if elapsed < 0.15:
                await asyncio.sleep(0.15 - elapsed)

            google = await fetch_google_books(http, title, author)
            last_request_time = time.time()

            goals = seed_goals
            if anthropic_client and google and google.get("description"):
                goals = await classify_goals_with_claude(
                    anthropic_client, title, author, google["description"], seed_goals
                )
                await asyncio.sleep(0.1)  # Claude rate limit buffer

            book = {
                "title": title,
                "author": author,
                "age_min": age_min,
                "age_max": age_max,
                "learning_goals": goals,
                "awards": awards,
                **(google or {}),
            }

            result = await insert_or_enrich(conn, book)
            if result == "inserted":
                inserted += 1
                print(f"  ✅ inserted")
            elif result == "enriched":
                enriched += 1
                print(f"  🔄 enriched")
            elif result == "skipped":
                skipped += 1
                print(f"  ⏭  skipped")
            else:
                errors += 1
                print(f"  ❌ error")

    after = await conn.fetchval("SELECT COUNT(*) FROM books WHERE is_children_book = TRUE")
    await conn.close()

    print(f"\n{'='*55}")
    print(f"DONE")
    print(f"  Inserted:  {inserted}")
    print(f"  Enriched:  {enriched}")
    print(f"  Skipped:   {skipped}")
    print(f"  Errors:    {errors}")
    print(f"  Children's books: {before} → {after} (+{after - before})")


if __name__ == "__main__":
    asyncio.run(main())
